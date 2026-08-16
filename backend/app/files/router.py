import os
import logging
import shutil
import uuid
from datetime import datetime
from typing import List, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.models import File as FileModel, Folder, FolderPermission, User, DocumentStatus, DocTypeSchema
from app.schemas import FileResponse as FileResponseSchema, FileCreate, FileUpdate
from app.auth.auth import get_current_user
from app.config import settings
from app.spark_transfer import spark_transfer_enabled, transfer_to_spark, SPARK_SHARED_DIR
from app.rbac import readable_folder_ids, writable_folder_ids, can_read_file_folder

router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)


# ==================== HELPERS ====================
# Katalog zapisu dokumentów — Z KONFIGURACJI (STORAGE_PATH), nie wpisany na sztywno.
#
# Wcześniej stała była zaszyta jako "/data/shared_docs" z awaryjnym zejściem do katalogu
# projektu, gdy tamtej ścieżki nie ma. Przy drugiej instancji (własny wolumen pod
# /data/hirs_shared_docs) warunek nie trafiał i pliki lądowały w katalogu WEWNĄTRZ
# kontenera: n8n ich nie widział, parsowanie padało natychmiast, a odtworzenie kontenera
# skasowałoby je bezpowrotnie. Ścieżka jest konfigurowalna od dawna — tylko ten fragment
# o tym nie wiedział.
#
# Fallback zostaje dla uruchomienia poza Dockerem (deweloperskie `uvicorn` z repo).
_PROJECT_ROOT_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "shared_docs")
STORAGE_DIR = settings.STORAGE_PATH or _PROJECT_ROOT_SHARED

# Publiczny adres backendu widziany z n8n (do callbacków statusu).
# Dev lokalny: http://<IP-PC-w-LAN>:8001, Spark: http://192.168.1.34:8083
BACKEND_CALLBACK_URL = os.getenv("BACKEND_CALLBACK_URL", "http://192.168.1.34:8083").rstrip("/")


def build_webhook_payload(file_id: int, file_path: str, folder_id: int | None = None,
                          uzytkownik: str | None = None) -> dict:
    """Zbuduj payload webhooka dla n8n z gotowym URL-em do aktualizacji statusu.

    `folder_id` trafia do payloadu Qdranta (Default Data Loader) i służy do
    filtrowania RBAC w czacie (Faza C). None = plik w katalogu głównym.

    `uzytkownik` — kto wgrał plik; idzie wyłącznie do raportu e-mail z parsowania.
    """
    return {
        "file_id": file_id,
        "file_path": file_path,
        "folder_id": folder_id,
        "status_update_url": f"{BACKEND_CALLBACK_URL}/api/webhook/file/{file_id}/status",
        # Kolekcja TEJ instancji. Jeden workflow n8n obsługuje wiele wdrożeń — bez tego
        # dokumenty demo trafiłyby do indeksu klienta (nazwa kolekcji była w n8n stałą).
        "collection": settings.QDRANT_COLLECTION,
        # Dane do raportu e-mail o parsowaniu. Ten sam workflow wysyła raporty z OBU
        # wdrożeń, więc bez nazwy instancji raport z demo wyglądał jak raport z systemu
        # klienta — zdarzyło się 2026-08-10 i kosztowało szukanie pliku w złej bazie.
        "instancja": settings.APP_NAME,
        "uzytkownik": uzytkownik or "nieznany",
    }


def get_mime_type(filename: str) -> str:
    """Determine MIME type from file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "odt": "application/vnd.oasis.opendocument.text",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt": "application/vnd.ms-powerpoint",
    }
    return mime_map.get(ext, "application/octet-stream")


def get_file_icon(filename: str) -> str:
    """Get icon name based on file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    icon_map = {
        "pdf": "pdf",
        "docx": "docx",
        "doc": "docx",
        "odt": "docx",
        "xlsx": "xlsx",
        "xls": "xlsx",
        "pptx": "pptx",
        "ppt": "pptx",
    }
    return icon_map.get(ext, "file")


def get_extension(filename: str) -> str:
    """Get file extension."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# ==================== ENDPOINTS ====================
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder_id: Optional[int] = Form(None, description="Folder ID where the file should be uploaded"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a file (admin lub rola z prawem Zapis do folderu docelowego)."""
    logger.debug(f"[UPLOAD] folder_id={folder_id}, filename={file.filename}")
    # RBAC: admin wszędzie; nie-admin tylko do folderu, w którym jego rola ma Zapis.
    writable = writable_folder_ids(current_user, db)
    if writable is not None:
        if folder_id is None:
            raise HTTPException(
                status_code=403,
                detail="Wgrywanie do katalogu głównego jest zarezerwowane dla administratora.",
            )
        if folder_id not in writable:
            raise HTTPException(
                status_code=403,
                detail="Brak uprawnień do zapisu w tym folderze.",
            )

    # Read file content for size check
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB
        raise HTTPException(status_code=413, detail="Plik jest za duży. Maksymalny rozmiar to 100MB.")

    # Reset file position for later reading
    file.file.seek(0)

    # Validate file type against admin-configured whitelist (Ustawienia aplikacji).
    # Whitelist musi odpowiadać gałęziom "Switch on file ext" w workflow n8n —
    # inaczej plik zostałby przyjęty, ale utknął bez obsługi.
    from app.settings.router import _load_cache_from_db, get_allowed_extensions
    _load_cache_from_db(db)
    allowed_extensions = get_allowed_extensions()
    ext = get_extension(file.filename)
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Nieobsługiwany typ pliku '.{ext}'. Dozwolone: {', '.join(sorted(allowed_extensions))}"
        )

    # Sprawdź, czy wskazany folder istnieje (przynależność jest LOGICZNA — trzymana
    # w bazie, nie w układzie katalogów; patrz niżej).
    if folder_id:
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            logger.warning(f"[UPLOAD] Folder {folder_id} nie istnieje")
            raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    # Ścieżka zapisu: OSOBNY KATALOG NA PLIK (losowy identyfikator) + ORYGINALNA nazwa.
    # - katalog gwarantuje unikalność, więc dwa pliki o tej samej nazwie nie nadpisują
    #   się nawzajem (wcześniej `open(..., "wb")` po cichu nadpisywał);
    # - nazwa pliku MUSI zostać nietknięta: chunki w Qdrancie zapisują
    #   `metadata.filename` wyciągnięty z fizycznej ścieżki, a backend dopasowuje po
    #   niej źródła czatu do dokumentów (klikalne cytowania, etykiety typu);
    # - układ katalogów nie odwzorowuje już drzewa folderów aplikacji — folder to
    #   informacja logiczna w bazie, dzięki czemu zmiana nazwy folderu i przenoszenie
    #   plików nie wymagają ruszania dysku (ani lokalnie, ani na Sparku).
    safe_name = os.path.basename(file.filename)
    relative_path = f"{uuid.uuid4().hex}/{safe_name}"
    storage_path = os.path.join(STORAGE_DIR, relative_path)

    os.makedirs(os.path.dirname(storage_path) or STORAGE_DIR, exist_ok=True)

    # Save file - write the content we already read
    with open(storage_path, "wb") as buffer:
        buffer.write(content)

    # Get file size
    file_size = os.path.getsize(storage_path)

    # >>> DEV MODE: transfer pliku na Sparka przez SSH <<<
    # Lokalny backend kopiuje plik do wolumenu shared_docs na Sparku,
    # aby n8n (uruchomiony na Sparku) widział go pod tą samą ścieżką
    # co przy uploadzie przez aplikację na Sparku (/data/shared_docs/...).
    effective_path = storage_path
    if spark_transfer_enabled():
        try:
            effective_path = transfer_to_spark(storage_path, relative_path)
        except RuntimeError as e:
            logger.error(f"[UPLOAD] Transfer na Sparka nie powiódł się: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Nie udało się przesłać pliku na Sparka: {e}"
            )

    # Create DB record (file_path = ścieżka widziana przez n8n/backend na Sparku)
    db_file = FileModel(
        # nazwa w bazie MUSI być identyczna z fizyczną (dopasowanie źródeł czatu po nazwie)
        filename=safe_name,
        file_path=effective_path,
        mime_type=get_mime_type(file.filename),
        size=file_size,
        folder_id=folder_id,
        uploaded_by=current_user.id,
        status=DocumentStatus.PENDING,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # >>> Kolejka: dyspozytor uruchomi przetwarzanie gdy przyjdzie kolej <<<
    # Plik pozostaje w PENDING ("W kolejce (n8n)"). Dyspozytor wyśle webhook
    # do n8n tylko jeśli żaden inny plik nie jest w PROCESSING (1 plik naraz).
    from app.dispatcher import try_dispatch_next
    dispatch_result = await try_dispatch_next(db)
    logger.info(f"[UPLOAD] Dispatch po uploadzie pliku {db_file.id}: {dispatch_result}")
    db.refresh(db_file)
    # <<< END kolejka >>>

    folder_obj = db_file.folder
    uploader_obj = db_file.uploader
    folder_dict = {"id": folder_obj.id, "name": folder_obj.name, "path": folder_obj.path} if folder_obj else None
    uploader_dict = {"id": uploader_obj.id, "username": uploader_obj.username, "email": uploader_obj.email} if uploader_obj else None

    return {
        "id": db_file.id,
        "filename": db_file.filename,
        "file_path": db_file.file_path,
        "mime_type": db_file.mime_type,
        "size": db_file.size,
        "folder_id": db_file.folder_id,
        "uploaded_by": db_file.uploaded_by,
        "doc_type": db_file.doc_type,
        "original_filename": db_file.original_filename,
        "status": db_file.status,
        "created_at": db_file.created_at,
        "updated_at": db_file.updated_at,
        "folder": folder_dict,
        "uploader": uploader_dict,
    }


@router.get("/", response_model=List[FileResponseSchema])
def list_files(
    folder_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    mime_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List files with optional filters.
    
    When folder_id is not specified (None), show only root files (folder_id IS NULL).
    When folder_id=0, show all files (legacy behavior).
    When folder_id=<int>, show files in that specific folder.
    """
    # RBAC: admin widzi wszystko; nie-admin tylko pliki z folderów dozwolonych
    # dla jego roli (z dziedziczeniem po ścieżce). Pliki w rootcie = tylko admin.
    readable = readable_folder_ids(current_user, db)
    if readable is not None and not readable:
        return []  # brak dostępu do jakiegokolwiek folderu

    query = db.query(FileModel)

    if folder_id is None:
        # No folder_id specified - show only root files (folder_id IS NULL)
        query = query.filter(FileModel.folder_id == None)
    elif folder_id == 0:
        # folder_id=0 is special - show all files (legacy behavior)
        pass  # No filter applied
    else:
        # Specific folder - show files in that folder
        query = query.filter(FileModel.folder_id == folder_id)

    # Nałóż ograniczenie widoczności po folderach (nie dotyczy admina).
    # `in_(readable)` nie obejmuje NULL, więc pliki w rootcie znikają dla nie-admina.
    if readable is not None:
        query = query.filter(FileModel.folder_id.in_(readable))
    if status:
        query = query.filter(FileModel.status == status)
    if mime_type:
        query = query.filter(FileModel.mime_type == mime_type)
    if search:
        query = query.filter(or_(
            FileModel.filename.ilike(f"%{search}%"),
        ))

    # Kolejność alfabetyczna po nazwie. Sortujemy w bazie, a nie po pobraniu:
    # zapytanie ma limit, więc sortowanie dopiero w przeglądarce układałoby
    # alfabetycznie wyłącznie pobraną porcję i ukrywało resztę plików.
    files = query.order_by(FileModel.filename.asc()).offset(skip).limit(limit).all()

    result = []
    for f in files:
        folder_data = None
        if f.folder:
            folder_data = {"id": f.folder.id, "name": f.folder.name, "path": f.folder.path}

        uploader_data = None
        if f.uploader:
            uploader_data = {"id": f.uploader.id, "username": f.uploader.username, "email": f.uploader.email}

        result.append({
            "id": f.id,
            "filename": f.filename,
            "file_path": f.file_path,
            "mime_type": f.mime_type,
            "size": f.size,
            "folder_id": f.folder_id,
            "uploaded_by": f.uploaded_by,
            "doc_type": f.doc_type,
            "original_filename": f.original_filename,
            "status": f.status,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
            "folder": folder_data,
            "uploader": uploader_data,
        })

    return result


# ==================== QUEUE & STATUS ENDPOINTS (must be BEFORE parameterized routes) ====================
@router.get("/queue")
def list_file_queue(
    status: Optional[str] = Query(None, description="Filter by status (optional)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get files with processing queue status (for File Queue page).
    
    Returns files from the files table with their DocumentStatus, which represents
    the processing queue status (W kolejce, Parsowanie, Przetworzono, etc.)
    """
    # RBAC: admin widzi wszystko; nie-admin tylko pliki z dozwolonych folderów.
    readable = readable_folder_ids(current_user, db)
    if readable is not None and not readable:
        return []

    query = db.query(FileModel)
    if readable is not None:
        query = query.filter(FileModel.folder_id.in_(readable))

    if status:
        query = query.filter(FileModel.status == status)

    # NAJNOWSZE NA GÓRZE — kolejka służy do pilnowania świeżo wgranych plików, więc
    # liczy się czas dodania, a nie nazwa. (Alfabetycznie układa się lista na stronie
    # Pliki; tam szuka się dokumentu po nazwie.) `id` jako drugi warunek rozstrzyga
    # pliki wgrane w tej samej sekundzie — bez tego ich kolejność byłaby przypadkowa.
    # Sortujemy w bazie, a nie po pobraniu: zapytanie ma limit, więc sortowanie
    # dopiero w przeglądarce ułożyłoby wyłącznie pobraną porcję.
    files = (query.order_by(FileModel.created_at.desc(), FileModel.id.desc())
             .offset(skip).limit(limit).all())
    
    result = []
    for f in files:
        folder_data = None
        if f.folder:
            folder_data = {"id": f.folder.id, "name": f.folder.name, "path": f.folder.path}
        
        uploader_data = None
        if f.uploader:
            uploader_data = {"id": f.uploader.id, "username": f.uploader.username, "email": f.uploader.email}
        
        # Powód błędu, czas parsowania oraz wynik klasyfikacji (#7B-2) z metadanych
        error_message = None
        processing_seconds = None
        doc_type = None
        doc_fields = None
        doc_type_verified = False
        if isinstance(f.metadata_, dict):
            error_message = f.metadata_.get("error")
            processing_seconds = f.metadata_.get("processing_seconds")
            doc_type = f.metadata_.get("doc_type")
            doc_fields = f.metadata_.get("doc_fields")
            doc_type_verified = bool(f.metadata_.get("doc_type_verified"))

        result.append({
            "id": f.id,
            "document_id": None,  # File doesn't have document_id, keeping for compatibility
            "file_name": f.filename,
            "status": f.status.value if hasattr(f.status, 'value') else str(f.status),
            "page_count": 0,  # Files don't have page count yet
            "error_message": error_message,
            "processing_seconds": processing_seconds,
            "doc_type": doc_type,
            "doc_fields": doc_fields,
            "doc_type_verified": doc_type_verified,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "started_at": None,
            "completed_at": None,
            "folder": folder_data,
            "uploader": uploader_data,
        })
    
    return result


class RenamePreviewRequest(BaseModel):
    file_ids: list[int]


class RenameItem(BaseModel):
    file_id: int
    filename: str          # nazwa docelowa (z podglądu albo wpisana ręcznie)


class RenameRequest(BaseModel):
    items: list[RenameItem]


def _rozszerzenie(nazwa: str) -> str:
    return os.path.splitext(nazwa or "")[1].lstrip(".").lower()


def _propozycje_nazw(pliki: list[FileModel], db: Session) -> list[dict]:
    """Dla każdego pliku: nazwa proponowana albo powód, dla którego jej nie ma.

    Kolizje rozstrzygamy wobec WSZYSTKICH nazw w bazie oraz wobec propozycji już
    wydanych w tej partii — inaczej dwa zarządzenia o tym samym numerze dostałyby
    identyczną nazwę i funkcja tworzyłaby problem, który ma leczyć.
    """
    from app.files.naming import build_filename, unique_filename

    wzorce = {
        sch.slug: (sch.name_pattern or "")
        for sch in db.query(DocTypeSchema).all()
    }
    zajete = {
        n for (n,) in db.query(FileModel.filename).all() if n
    } - {p.filename for p in pliki}

    wynik = []
    for f in pliki:
        meta = f.metadata_ if isinstance(f.metadata_, dict) else {}
        doc_type = meta.get("doc_type")
        pozycja = {
            "file_id": f.id,
            "filename": f.filename,
            "doc_type": doc_type,
            "proponowana": None,
            "problem": None,
        }
        if not doc_type or doc_type == "inny":
            pozycja["problem"] = "dokument nie ma rozpoznanej kategorii"
        elif not wzorce.get(doc_type):
            pozycja["problem"] = f"kategoria „{doc_type}” nie ma wzorca nazwy"
        else:
            nazwa, braki = build_filename(
                wzorce[doc_type], doc_type, meta.get("doc_fields") or {},
                _rozszerzenie(f.filename),
            )
            if nazwa is None:
                pozycja["problem"] = "brak pól: " + ", ".join(braki)
            else:
                nazwa = unique_filename(nazwa, zajete)
                zajete.add(nazwa)
                pozycja["proponowana"] = nazwa
        wynik.append(pozycja)
    return wynik


@router.post("/rename-preview")
def rename_preview(
    payload: RenamePreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Co się stanie po nadaniu nazw — BEZ wykonywania czegokolwiek.

    Operacja dotyka kilkudziesięciu plików naraz i zmienia to, pod czym ludzie
    znają dokumenty. Bez listy „stara nazwa → nowa nazwa" nikt nie odważy się jej
    kliknąć, i słusznie.
    """
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="Nie wskazano plików.")
    pliki = db.query(FileModel).filter(FileModel.id.in_(payload.file_ids)).all()
    return {"pozycje": _propozycje_nazw(pliki, db)}


@router.post("/rename")
def rename_files(
    payload: RenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Nadaj plikom nowe nazwy (z podglądu albo wpisane ręcznie).

    Nazwa żyje w czterech miejscach i wszystkie trzeba ruszyć razem: kolumna
    w bazie, plik na dysku, `file_path` (to jego dostaje n8n) oraz
    `metadata.filename` w chunkach i streszczeniu w Qdrancie — bo to stamtąd
    bierze się nazwa pokazywana pod odpowiedzią czatu.

    Oryginalną nazwę zapamiętujemy przy pierwszej zmianie: pozwala cofnąć operację
    i nie gubi tego, pod czym użytkownik pamięta dokument.
    """
    from app.files.naming import unique_filename
    from app.qdrant_client import set_filename, set_summary_filename
    from app.text_utils import slugify

    if not payload.items:
        raise HTTPException(status_code=400, detail="Nie wskazano plików.")

    writable = writable_folder_ids(current_user, db)
    zajete = {n for (n,) in db.query(FileModel.filename).all() if n}

    zmienione, pominiete = [], []
    for item in payload.items:
        f = db.query(FileModel).filter(FileModel.id == item.file_id).first()
        if not f:
            pominiete.append({"file_id": item.file_id, "powod": "plik nie istnieje"})
            continue
        if writable is not None and (f.folder_id is None or f.folder_id not in writable):
            pominiete.append({"file_id": f.id, "powod": "brak prawa zapisu w folderze"})
            continue
        if f.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
            pominiete.append({"file_id": f.id, "powod": "plik jest w trakcie przetwarzania"})
            continue

        # Nazwę wpisaną ręcznie czyścimy tak samo jak generowaną — cały sens
        # operacji to JEDEN spójny system nazw, a nie druga furtka na spacje
        # i znaki zakazane w systemie plików.
        ext = _rozszerzenie(item.filename) or _rozszerzenie(f.filename)
        rdzen = slugify(os.path.splitext(item.filename or "")[0], max_length=120)
        if not rdzen:
            pominiete.append({"file_id": f.id, "powod": "pusta nazwa"})
            continue
        nowa = f"{rdzen}.{ext}" if ext else rdzen
        if nowa == f.filename:
            continue
        nowa = unique_filename(nowa, zajete - {f.filename})
        zajete.add(nowa)

        stara = f.filename
        sciezka = _zmien_nazwe_na_dysku(f.file_path, nowa)
        if sciezka:
            f.file_path = sciezka
        if not f.original_filename:
            f.original_filename = stara
        f.filename = nowa
        zmienione.append({"file_id": f.id, "z": stara, "na": nowa, "na_dysku": bool(sciezka)})

    db.commit()

    for z in zmienione:                       # Qdrant dopiero po zatwierdzeniu w bazie
        set_filename(z["file_id"], z["na"])
        set_summary_filename(z["file_id"], z["na"])

    logger.info(
        f"[RENAME] {current_user.username}: zmieniono nazwę {len(zmienione)} plik(ów); "
        f"pominięto {len(pominiete)}"
    )
    return {"zmienione": zmienione, "pominiete": pominiete}


def _zmien_nazwe_na_dysku(sciezka: str | None, nowa_nazwa: str) -> str | None:
    """Zmienia nazwę pliku i jego konwersji; zwraca nową ścieżkę albo None.

    None oznacza, że pliku nie ma na tej maszynie — tak jest w środowisku
    deweloperskim, gdzie dokumenty leżą na Sparku. Zmieniamy wtedy tylko nazwę
    widoczną w aplikacji, a `file_path` zostawiamy wskazujący na realny plik.
    """
    if not sciezka or not os.path.exists(sciezka):
        return None
    katalog = os.path.dirname(sciezka)
    stary_rdzen = os.path.splitext(os.path.basename(sciezka))[0]
    nowy_rdzen = os.path.splitext(nowa_nazwa)[0]
    docelowa = os.path.join(katalog, nowa_nazwa)
    try:
        os.rename(sciezka, docelowa)
        # Konwersje (odt → docx → pdf) leżą obok pod tym samym rdzeniem; gdyby
        # zostały ze starą nazwą, podgląd przestałby je znajdować.
        for plik in os.listdir(katalog):
            rdzen, ext = os.path.splitext(plik)
            if rdzen == stary_rdzen and plik != nowa_nazwa:
                os.rename(os.path.join(katalog, plik), os.path.join(katalog, nowy_rdzen + ext))
    except OSError as e:
        logger.warning(f"[RENAME] Zmiana nazwy na dysku nieudana ({sciezka}): {e}")
        return None
    return docelowa


class MoveFilesRequest(BaseModel):
    file_ids: list[int]
    folder_id: Optional[int] = None   # None = katalog główny (tylko admin)


@router.post("/move")
def move_files(
    payload: MoveFilesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Przenieś pliki do innego folderu (pojedynczo lub wiele naraz).

    Przenoszenie jest LOGICZNE — zmienia się `files.folder_id`, plik zostaje na dysku
    tam, gdzie był (ścieżka fizyczna pozostaje ważna). Dodatkowo aktualizujemy
    `metadata.folder_id` w chunkach Qdranta, bo po tym polu czat filtruje dostęp wg
    roli — bez tego przeniesiony dokument nadal odpowiadałby staremu folderowi.

    Uprawnienia: potrzebne prawo Zapis w folderze ŹRÓDŁOWYM i DOCELOWYM
    (katalog główny = tylko admin). Pliki w trakcie przetwarzania są pomijane —
    parsowanie właśnie z nich korzysta.
    """
    from app.qdrant_client import set_folder_id, set_summary_folder_id

    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="Nie wskazano plików do przeniesienia.")

    writable = writable_folder_ids(current_user, db)   # None = admin (wszędzie)

    # Folder docelowy
    target_id = payload.folder_id
    if target_id is not None:
        target = db.query(Folder).filter(Folder.id == target_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Folder docelowy nie istnieje.")
        if writable is not None and target_id not in writable:
            raise HTTPException(status_code=403, detail="Brak prawa zapisu w folderze docelowym.")
    elif writable is not None:
        raise HTTPException(status_code=403, detail="Tylko administrator może przenosić do katalogu głównego.")

    przeniesione, pominiete = [], []
    for fid in payload.file_ids:
        f = db.query(FileModel).filter(FileModel.id == fid).first()
        if not f:
            pominiete.append({"file_id": fid, "powod": "plik nie istnieje"})
            continue
        if writable is not None and (f.folder_id is None or f.folder_id not in writable):
            pominiete.append({"file_id": fid, "powod": "brak prawa zapisu w folderze źródłowym"})
            continue
        if f.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
            pominiete.append({"file_id": fid, "powod": "plik jest w trakcie przetwarzania"})
            continue
        if f.folder_id == target_id:
            continue  # już jest na miejscu
        f.folder_id = target_id
        przeniesione.append(fid)

    db.commit()

    # Qdrant dopiero po zatwierdzeniu zmian w bazie (best-effort)
    for fid in przeniesione:
        set_folder_id(fid, target_id)
        set_summary_folder_id(fid, target_id)  # streszczenie filtrowane tym samym polem

    logger.info(
        f"[MOVE] {current_user.username}: przeniesiono {len(przeniesione)} plik(ów) "
        f"do folderu {target_id}; pominięto {len(pominiete)}"
    )
    return {"moved": przeniesione, "skipped": pominiete}


class DocTypeOverride(BaseModel):
    doc_type: str  # slug typu z rejestru albo "inny"


@router.patch("/{file_id}/doc-type")
async def override_doc_type(
    file_id: int,
    payload: DocTypeOverride,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ręczna korekta kategorii dokumentu (#7B-2) + re-ekstrakcja pól dla nowego typu.

    Ustawia `doc_type` i flagę `doc_type_verified` (trwała korekta — auto-klasyfikacja
    jej nie nadpisze). Dla typu innego niż „inny" wyciąga pola dla nowego typu jednym
    wywołaniem modelu (tekst z Qdranta; respektuje arbitraż modelu). Tylko admin.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zmieniać kategorię.")

    file = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    slug = (payload.doc_type or "").strip()
    schema_row = None
    if slug and slug != "inny":
        schema_row = db.query(DocTypeSchema).filter(DocTypeSchema.slug == slug).first()
        if not schema_row:
            raise HTTPException(status_code=400, detail=f"Nieznany typ: {slug}")

    # Re-ekstrakcja pól dla nowego typu (jeśli to konkretny typ)
    doc_fields: dict = {}
    if schema_row:
        from app.qdrant_client import get_text_by_file_id
        from app.doc_extract import extract_fields
        from app.activity import extraction_started, extraction_finished
        import asyncio as _asyncio
        text = await _asyncio.to_thread(get_text_by_file_id, file_id)
        if text:
            extraction_started()  # nie koliduj z parsowaniem/czatem o model
            try:
                schema_dict = {
                    "slug": schema_row.slug, "name": schema_row.name,
                    "fields": schema_row.fields or [],
                }
                doc_fields = await extract_fields(schema_dict, text, file.filename)
            except Exception as e:
                logger.warning(f"[OVERRIDE] Plik {file_id}: re-ekstrakcja pól nieudana: {e}")
            finally:
                extraction_finished()
                from app.dispatcher import try_dispatch_next
                try:
                    await try_dispatch_next(db)  # wznów kolejkę wstrzymaną na czas ekstrakcji
                except Exception:
                    pass

    meta = dict(file.metadata_ or {})
    meta["doc_type"] = slug
    meta["doc_type_verified"] = True
    meta["doc_fields"] = doc_fields
    file.metadata_ = meta
    db.commit()

    # Skorygowany typ trafia też do chunków w Qdrancie (best-effort)
    import asyncio as _aio
    from app.qdrant_client import set_doc_type
    await _aio.to_thread(set_doc_type, file_id, slug)
    logger.info(f"[OVERRIDE] Plik {file_id}: kategoria ręcznie → {slug} (pól={len(doc_fields)})")
    return {"file_id": file_id, "doc_type": slug, "doc_fields": doc_fields, "doc_type_verified": True}


@router.get("/status-summary")
def get_file_status_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get file counts grouped by status.
    
    Returns a dictionary with status names as keys and counts as values.
    """
    # Admin sees all files; other users only their own
    query = db.query(FileModel)
    if not current_user.is_admin:
        query = query.filter(FileModel.uploaded_by == current_user.id)

    # Group by status and count
    from sqlalchemy import func
    status_counts = query.group_by(FileModel.status).with_entities(
        FileModel.status, func.count(FileModel.id)
    ).all()
    
    summary = {}
    for status, count in status_counts:
        status_str = status.value if hasattr(status, 'value') else str(status)
        summary[status_str] = count
    
    return summary


@router.get("/{file_id}", response_model=FileResponseSchema)
def get_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get file metadata."""
    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    # RBAC: dostęp po roli do folderu (z dziedziczeniem); admin zawsze,
    # pliki w rootcie tylko admin.
    readable = readable_folder_ids(current_user, db)
    if not can_read_file_folder(file_obj.folder_id, readable):
        raise HTTPException(status_code=403, detail="Brak dostępu do tego pliku.")

    folder_data = None
    if file_obj.folder:
        folder_data = {"id": file_obj.folder.id, "name": file_obj.folder.name, "path": file_obj.folder.path}

    uploader_data = None
    if file_obj.uploader:
        uploader_data = {"id": file_obj.uploader.id, "username": file_obj.uploader.username, "email": file_obj.uploader.email}

    return {
        "id": file_obj.id,
        "filename": file_obj.filename,
        "file_path": file_obj.file_path,
        "mime_type": file_obj.mime_type,
        "size": file_obj.size,
        "folder_id": file_obj.folder_id,
        "uploaded_by": file_obj.uploaded_by,
        "doc_type": file_obj.doc_type,
        "original_filename": file_obj.original_filename,
        "status": file_obj.status,
        "created_at": file_obj.created_at,
        "updated_at": file_obj.updated_at,
        "folder": folder_data,
        "uploader": uploader_data,
    }


def _resolve_local_path(file_path: str) -> str:
    """Zmapuj ścieżkę z DB na lokalnie istniejący plik.

    W trybie dev DB przechowuje ścieżkę Sparka (/data/shared_docs/...),
    ale lokalna kopia leży w STORAGE_DIR — spróbuj obu.
    Gdy lokalnej kopii brak (np. po rebuildzie kontenera), a transfer SSH
    jest włączony — pobierz plik ze Sparka do lokalnego cache.
    """
    if os.path.exists(file_path):
        return file_path
    prefix = SPARK_SHARED_DIR.rstrip("/") + "/"
    if file_path.startswith(prefix):
        candidate = os.path.join(STORAGE_DIR, file_path[len(prefix):])
        if os.path.exists(candidate):
            return candidate
        # Fallback: ściągnij ze Sparka (dev mode)
        if spark_transfer_enabled():
            try:
                from app.spark_transfer import fetch_from_spark
                fetch_from_spark(file_path, candidate)
                return candidate
            except RuntimeError as e:
                logger.error(f"[DOWNLOAD] Nie udało się pobrać ze Sparka: {e}")
    return file_path


@router.get("/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download a file."""
    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    # RBAC: bez tego każdy zalogowany mógł pobrać dowolny plik po id.
    readable = readable_folder_ids(current_user, db)
    if not can_read_file_folder(file_obj.folder_id, readable):
        raise HTTPException(status_code=403, detail="Brak dostępu do tego pliku.")

    local_path = _resolve_local_path(file_obj.file_path)
    if not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="Plik nie istnieje na dysku.")

    return FileResponse(
        path=local_path,
        filename=file_obj.filename,
        media_type=file_obj.mime_type or "application/octet-stream",
    )


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a file (admin lub rola z prawem Zapis do folderu pliku)."""
    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    # RBAC: admin wszędzie; nie-admin tylko w folderze z prawem Zapis (root = admin).
    writable = writable_folder_ids(current_user, db)
    if writable is not None and (file_obj.folder_id is None or file_obj.folder_id not in writable):
        raise HTTPException(status_code=403, detail="Brak uprawnień do usunięcia tego pliku.")

    # Usuń wektory z Qdranta (żeby usunięty/wygasły dokument nie odpowiadał
    # już w czacie). Best-effort — awaria Qdranta nie blokuje usunięcia pliku.
    from app.qdrant_client import delete_sections, delete_summary, delete_vectors_by_file_id
    qdrant_result = delete_vectors_by_file_id(file_obj.id)
    delete_summary(file_obj.id)   # razem z fragmentami znika streszczenie dokumentu
    delete_sections(file_obj.id)  # oraz jego streszczenia sekcyjne (zob. app/sekcje.py)

    # Usuń plik z dysku. Lokalnie zawsze; dodatkowo kopię na Sparku, ale TYLKO w
    # trybie deweloperskim — tam istnieje druga kopia (most SSH). W docelowym
    # wdrożeniu aplikacja działa na Sparku, `file_path` jest ścieżką lokalną i
    # wystarczy os.remove poniżej.
    # Pliki pochodne: formaty wymagające konwersji zostawiają obok źródła plik
    # o tej samej nazwie — PDF (ścieżka rasteryzacji) lub DOCX (ścieżka tekstowa
    # dla .odt). Usuwamy je razem z oryginałem.
    def _derived_files(path: str) -> list[str]:
        stem, ext = os.path.splitext(path)
        ext = ext.lower()
        return [f"{stem}.{d}" for d in ("pdf", "docx") if ext not in ("", f".{d}")]

    local_path = _resolve_local_path(file_obj.file_path)
    for p in [local_path, *_derived_files(local_path)]:
        if os.path.exists(p):
            os.remove(p)
    # katalog pliku (schemat <uuid>/<nazwa>) usuwamy, gdy został pusty
    parent = os.path.dirname(local_path)
    if parent and parent != STORAGE_DIR and os.path.isdir(parent) and not os.listdir(parent):
        os.rmdir(parent)

    spark_result = None
    if spark_transfer_enabled():
        from app.spark_transfer import delete_from_spark
        spark_result = delete_from_spark(file_obj.file_path)
        for derived in _derived_files(file_obj.file_path):
            delete_from_spark(derived)

    # Delete DB record
    db.delete(file_obj)
    db.commit()

    return {"message": "Plik został usunięty.", "qdrant": qdrant_result, "spark": spark_result}


@router.put("/{file_id}", response_model=FileResponseSchema)
def update_file(
    file_id: int,
    file_update: FileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update file metadata (status, folder). Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może aktualizować pliki.")

    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    update_data = file_update.model_dump(exclude_unset=True)
    # Zmiana folderu TYLKO przez POST /api/files/move — tam aktualizowany jest też
    # `metadata.folder_id` w Qdrancie, po którym czat filtruje dostęp wg roli.
    # Ustawienie folderu tutaj rozjechałoby bazę z bazą wektorową (luka w dostępie).
    if "folder_id" in update_data:
        raise HTTPException(
            status_code=400,
            detail="Zmiana folderu przez ten endpoint jest niedozwolona — użyj /api/files/move.",
        )
    for field, value in update_data.items():
        setattr(file_obj, field, value)

    db.commit()
    db.refresh(file_obj)

    folder_data = None
    if file_obj.folder:
        folder_data = {"id": file_obj.folder.id, "name": file_obj.folder.name, "path": file_obj.folder.path}

    uploader_data = None
    if file_obj.uploader:
        uploader_data = {"id": file_obj.uploader.id, "username": file_obj.uploader.username, "email": file_obj.uploader.email}

    return {
        "id": file_obj.id,
        "filename": file_obj.filename,
        "file_path": file_obj.file_path,
        "mime_type": file_obj.mime_type,
        "size": file_obj.size,
        "folder_id": file_obj.folder_id,
        "uploaded_by": file_obj.uploaded_by,
        "doc_type": file_obj.doc_type,
        "original_filename": file_obj.original_filename,
        "status": file_obj.status,
        "created_at": file_obj.created_at,
        "updated_at": file_obj.updated_at,
        "folder": folder_data,
        "uploader": uploader_data,
    }


@router.get("/categories")
def get_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get file categories (by MIME type)."""
    # RBAC: zliczaj tylko pliki widoczne dla użytkownika.
    readable = readable_folder_ids(current_user, db)
    if readable is not None and not readable:
        return []

    def _scoped(q):
        return q.filter(FileModel.folder_id.in_(readable)) if readable is not None else q

    mime_types = _scoped(db.query(FileModel.mime_type).distinct()).all()
    categories = []
    for (mt,) in mime_types:
        ext = mt.split("/")[-1] if mt else ""
        categories.append({
            "mime_type": mt,
            "extension": ext,
            "icon": get_file_icon(f"file.{ext}"),
            "count": _scoped(db.query(FileModel).filter(FileModel.mime_type == mt)).count(),
        })
    return categories


@router.get("/folder/{folder_id}/files", response_model=List[FileResponseSchema])
def list_folder_files(folder_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get files in a specific folder."""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    # RBAC: nie-admin widzi pliki tylko w folderach dozwolonych dla jego roli.
    readable = readable_folder_ids(current_user, db)
    if readable is not None and folder_id not in readable:
        raise HTTPException(status_code=403, detail="Brak dostępu do tego folderu.")

    files = db.query(FileModel).filter(FileModel.folder_id == folder_id).all()

    result = []
    for f in files:
        folder_data = {"id": f.folder.id, "name": f.folder.name, "path": f.folder.path} if f.folder else None
        uploader_data = {"id": f.uploader.id, "username": f.uploader.username} if f.uploader else None
        result.append({
            "id": f.id,
            "filename": f.filename,
            "file_path": f.file_path,
            "mime_type": f.mime_type,
            "size": f.size,
            "folder_id": f.folder_id,
            "uploaded_by": f.uploaded_by,
            "doc_type": f.doc_type,
            "original_filename": f.original_filename,
            "status": f.status,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
            "folder": folder_data,
            "uploader": uploader_data,
        })

    return result



# ==================== Eksport listy do XLSX ====================
class EksportXlsxRequest(BaseModel):
    """Lista dokumentów do wyeksportowania — w kolejności, w jakiej widzi ją użytkownik."""
    file_ids: List[int]
    # Treść pytania — z niej powstaje nazwa pliku („zarządzenia 2009" → zarzadzenia-2009.xlsx)
    pytanie: Optional[str] = None


@router.post("/eksport-xlsx")
def eksport_listy_xlsx(
    payload: EksportXlsxRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zbuduj arkusz XLSX z listy dokumentów wskazanej przez odpowiedź czatu.

    Kolumny pochodzą z rejestru schematów, jeden arkusz na typ dokumentu —
    zob. app/eksport.py.

    UPRAWNIENIA: eksport przechodzi przez ten sam filtr, co lista plików. Nie może
    być furtką do dokumentów spoza uprawnień użytkownika, nawet gdyby ktoś podał
    identyfikatory ręcznie.
    """
    from fastapi.responses import Response
    from app.doc_schemas.router import get_active_schemas
    from app.eksport import naglowek_pobierania, nazwa_pliku, zbuduj_xlsx

    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="Pusta lista dokumentów.")
    if len(payload.file_ids) > 2000:
        raise HTTPException(status_code=400, detail="Lista jest za długa (maks. 2000).")

    readable = readable_folder_ids(current_user, db)
    rows = db.query(FileModel).filter(FileModel.id.in_(set(payload.file_ids))).all()
    dozwolone = {
        f.id: f for f in rows if can_read_file_folder(f.folder_id, readable)
    }

    # Kolejność Z EKRANU, nie z bazy: użytkownik widział listę ułożoną w konkretny
    # sposób (np. najnowsze zarządzenia u góry) i tego samego oczekuje w arkuszu.
    dokumenty = []
    for fid in payload.file_ids:
        f = dozwolone.get(fid)
        if f is None:
            continue
        meta = f.metadata_ if isinstance(f.metadata_, dict) else {}
        dokumenty.append({
            "filename": f.filename,
            "doc_type": meta.get("doc_type"),
            "doc_fields": meta.get("doc_fields") or {},
        })

    if not dokumenty:
        raise HTTPException(status_code=404, detail="Brak dokumentów do wyeksportowania.")

    schematy = {s["slug"]: s for s in get_active_schemas(db)}
    zawartosc = zbuduj_xlsx(dokumenty, schematy)
    nazwa = nazwa_pliku(dokumenty, schematy, payload.pytanie)
    pominiete = len(set(payload.file_ids)) - len(dozwolone)
    logger.info(
        f"[EKSPORT] user={current_user.username} pozycji={len(dokumenty)}"
        f"{f' (pominieto bez uprawnien: {pominiete})' if pominiete else ''} -> {nazwa}"
    )
    return Response(
        content=zawartosc,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": naglowek_pobierania(nazwa)},
    )
