"""
Webhook router dla n8n.

Endpointy:
- POST /api/webhook/file-notified — n8n informuje backend o nowym pliku
- PATCH /api/webhook/file/{file_id}/status — n8n aktualizuje status pliku
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ROLE_ADMIN, File as FileModel, DocumentStatus, User
from app.files.router import get_mime_type
from app.webhook_auth import verify_webhook_secret

logger = logging.getLogger(__name__)

# Cały router jest wywoływany przez n8n (nie przez przeglądarkę), więc zamiast
# JWT chroni go wspólny sekret w nagłówku X-Webhook-Secret.
router = APIRouter(
    prefix="/api/webhook",
    tags=["Webhooks"],
    dependencies=[Depends(verify_webhook_secret)],
)

# Referencje do zadań w tle (klasyfikacja #7B-2), żeby GC nie przerwał zadania
# przed zakończeniem (asyncio trzyma tylko słabe referencje do tasków).
_bg_tasks: set = set()


def _resolve_status(value: str) -> DocumentStatus:
    """Map an incoming status string (enum name or value, PL/EN) to DocumentStatus."""
    if isinstance(value, DocumentStatus):
        return value
    # Try enum name (e.g. "PENDING", "READY")
    normalized = value.strip()
    if normalized.upper() in DocumentStatus.__members__:
        return DocumentStatus[normalized.upper()]
    # Try enum value (e.g. "Przetworzono", "W kolejce (n8n)")
    for member in DocumentStatus:
        if member.value == normalized:
            return member
    # Legacy aliases used by n8n (old pipeline stage names map to PROCESSING)
    aliases = {
        "W KOLEJCE (N8N)": DocumentStatus.PENDING,  # dawna etykieta — zgodność wstecz
        "PROCESSED": DocumentStatus.READY,
        "PRZETWARZANIE": DocumentStatus.PROCESSING,
        "PARSOWANIE (DOCLING)": DocumentStatus.PROCESSING,
        "CHUNKOWANIE": DocumentStatus.PROCESSING,
        "WEKTORYZACJA (QDRANT)": DocumentStatus.PROCESSING,
        "PARSING": DocumentStatus.PROCESSING,
        "PENDING_CHUNKING": DocumentStatus.PROCESSING,
        "PENDING_VECTORIZE": DocumentStatus.PROCESSING,
    }
    if normalized.upper() in aliases:
        return aliases[normalized.upper()]
    raise HTTPException(
        status_code=400,
        detail=f"Nieznany status: '{value}'. Dozwolone: "
               f"{[m.name for m in DocumentStatus]} lub {[m.value for m in DocumentStatus]}"
    )


def _get_system_user_id(db: Session) -> int:
    """Return id of the 'system' user (used for files registered by n8n)."""
    user = db.query(User).filter(User.username == "system").first()
    if user:
        return user.id
    # Fallback: first admin account
    admin = db.query(User).filter(User.role == ROLE_ADMIN).first()
    if admin:
        return admin.id
    raise HTTPException(
        status_code=500,
        detail="Brak użytkownika systemowego ('system') — uruchom seed.sql."
    )


class FileNotification(BaseModel):
    """Powiadomienie o nowym pliku od n8n."""
    file_path: str  # pełna ścieżka do pliku na Sparku, np /home/marcin/zco-edm-app/shared_docs/uploads/umowa.pdf


class StatusUpdate(BaseModel):
    """Aktualizacja statusu pliku od n8n."""
    status: str = "PENDING"  # PENDING, PROCESSING, PROCESSED, ERROR
    ocr_result: str = None  # wynik OCR (markdown)
    metadata: dict = None  # dodatkowe metadane


@router.post("/file-notified")
async def file_notified(payload: FileNotification, db: Session = Depends(get_db)):
    """
    n8n informuje backend o nowym pliku.
    
    Backend tworzy rekord w bazie danych ze statusem PENDING.
    n8n samodzielnie przetwarza plik (Docling OCR, LLM analysis, etc.)
    i później aktualizuje status через PATCH /api/webhook/file/{id}/status
    """
    # Sprawdź czy plik istnieje
    if not os.path.exists(payload.file_path):
        raise HTTPException(status_code=404, detail=f"Brak pliku: {payload.file_path}")

    # Sprawdź czy rekord już istnieje
    existing = db.query(FileModel).filter(FileModel.file_path == payload.file_path).first()
    if existing:
        # Jeśli istnieje i ma status READY (Przetworzono), zignoruj
        if existing.status == DocumentStatus.READY:
            return {"file_id": existing.id, "status": existing.status, "message": "Plik juz przetworzony"}
        # Jeśli jest w trakcie przetwarzania, zaktualizuj status
        existing.status = DocumentStatus.PENDING
        db.commit()
        return {"file_id": existing.id, "status": "PENDING", "message": "Reuaktywacja pliku"}

    # Utwórz nowy rekord
    db_file = FileModel(
        filename=os.path.basename(payload.file_path),
        file_path=payload.file_path,
        mime_type=get_mime_type(payload.file_path),
        size=os.path.getsize(payload.file_path),
        status=DocumentStatus.PENDING,
        uploaded_by=_get_system_user_id(db),  # system upload (n8n)
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return {
        "file_id": db_file.id,
        "filename": db_file.filename,
        "file_path": db_file.file_path,
        "status": db_file.status,
        "message": "Plik zarejestrowany"
    }


@router.patch("/file/{file_id}/status")
async def update_file_status(file_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):  # noqa: C901
    """
    n8n aktualizuje status pliku po przetworzeniu.
    
    Moze zaktualizowac:
    - status: PENDING → PROCESSING → PROCESSED / ERROR
    - ocr_result: wynik z Docling (markdown)
    - metadata: dodatkowe dane (np. wyniki analizy LLM)
    """
    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie znaleziony")

    # Aktualizuj status (mapowanie stringa na DocumentStatus)
    new_status = _resolve_status(payload.status)

    # #7B-2 (opcja B): gdy n8n zgłasza READY, a rejestr niepusty, plik NIE przechodzi
    # jeszcze na „Przetworzono" — zostaje „Przetwarzanie" na czas klasyfikacji.
    # READY (i czas przetwarzania) ustawi run_extraction po jej zakończeniu.
    active_schemas: list = []
    if new_status == DocumentStatus.READY:
        from app.doc_schemas.router import get_active_schemas
        active_schemas = get_active_schemas(db)
    will_classify = new_status == DocumentStatus.READY and bool(active_schemas)

    # Jawny błąd z n8n bywa przejściowy (zmierzone: gm pada w oknach presji pamięci
    # hosta, a te same dane chwilę później przechodzą). Pierwszą nieudaną próbę
    # ponawiamy od razu — plik wraca do kolejki; dopiero wyczerpanie puli prób
    # kończy się statusem „Błąd przetwarzania". Ta sama pula co w watchdogu.
    from app.dispatcher import MAX_PARSE_ATTEMPTS
    proby = int((file_obj.metadata_ or {}).get("parse_attempts") or 1)
    retry_after_error = new_status == DocumentStatus.ERROR and proby < MAX_PARSE_ATTEMPTS
    if retry_after_error:
        logger.warning(
            f"[WEBHOOK] Plik {file_id} zgłosił błąd (próba {proby}/{MAX_PARSE_ATTEMPTS}) — ponawiam"
        )
        file_obj.status = DocumentStatus.PENDING
    else:
        file_obj.status = DocumentStatus.PROCESSING if will_classify else new_status

    # Aktualizuj OCR wynik
    if payload.ocr_result:
        file_obj.ocr_result = payload.ocr_result

    # Aktualizuj metadane — SCAL z istniejącymi (nie nadpisuj całości).
    # n8n przy błędzie może przysłać {"error": "..."} → trafia do UI kolejki.
    if payload.metadata:
        merged = dict(file_obj.metadata_ or {})
        merged.update(payload.metadata)
        file_obj.metadata_ = merged

    # Sukces parsowania kasuje ewentualny stary błąd i licznik prób (parsowanie
    # się udało — kolejne przetwarzanie tego pliku zaczyna liczenie od zera).
    if new_status == DocumentStatus.READY and isinstance(file_obj.metadata_, dict):
        if "error" in file_obj.metadata_ or "parse_attempts" in file_obj.metadata_:
            cleaned = dict(file_obj.metadata_)
            cleaned.pop("error", None)
            cleaned.pop("parse_attempts", None)
            file_obj.metadata_ = cleaned

    # Czas parsowania: licz przy prawdziwym końcu. ERROR i READY-bez-klasyfikacji — teraz;
    # READY-z-klasyfikacją — dopiero po niej (w run_extraction). Przy ponowieniu
    # po błędzie czasu nie liczymy — przebieg się nie skończył, zaraz startuje kolejny.
    if (new_status == DocumentStatus.ERROR and not retry_after_error) or (
        new_status == DocumentStatus.READY and not will_classify
    ):
        from app.dispatcher import mark_processing_finished
        mark_processing_finished(file_obj)

    db.commit()

    # >>> Kolejka: po zakończeniu przetwarzania <<<
    import logging
    dispatch_info = None
    if will_classify:
        # Plik zostaje „Przetwarzanie"; klasyfikacja w tle podnosi flagę (dyspozytor
        # wstrzymany), a po sobie ustawia READY i wznawia kolejkę.
        import asyncio
        from app.activity import extraction_started
        from app.doc_extract import run_extraction
        extraction_started()  # SYNCHRONICZNIE — dyspozytor od razu widzi zajętość
        task = asyncio.create_task(run_extraction(file_id, active_schemas, file_obj.filename))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
        dispatch_info = {"deferred": "extraction", "file_id": file_id}
    elif new_status in (DocumentStatus.READY, DocumentStatus.ERROR):
        from app.dispatcher import try_dispatch_next
        dispatch_info = await try_dispatch_next(db)

    if dispatch_info is not None:
        logging.getLogger(__name__).info(
            f"[WEBHOOK] Plik {file_id} zakończony ({new_status.name}); dispatch: {dispatch_info}"
        )
    # <<< END kolejka >>>

    return {
        "file_id": file_id,
        "status": file_obj.status.value if hasattr(file_obj.status, "value") else str(file_obj.status),
        "message": "Status zaktualizowany",
        "dispatch": dispatch_info,
    }


@router.get("/files/texts")
def get_files_texts(
    folder_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Teksty plików — dla workflow INDUKCJI schematów w n8n.

    Chroniony sekretem webhooka (dependency na routerze), więc n8n czyta gotowe
    sparsowane teksty bez własnego dostępu do Postgresa. Dane zostają w LAN Sparka
    (n8n i backend na tej samej sieci).

    Źródło tekstu: workflow parsowania NIE zapisuje `ocr_result` w Postgresie, więc
    tekst odtwarzamy z chunków w Qdrancie (patrz get_texts_by_folder). Jeśli plik
    ma jednak `ocr_result` w bazie (np. z przyszłego callbacku), ma on pierwszeństwo.
    Zwraca wyłącznie pliki, dla których udało się uzyskać niepusty tekst.
    """
    from app.qdrant_client import get_texts_by_folder

    q = db.query(FileModel)
    if folder_id is not None:
        q = q.filter(FileModel.folder_id == folder_id)
    files = q.order_by(FileModel.id.desc()).all()

    qdrant_texts = get_texts_by_folder(folder_id)

    out = []
    for f in files:
        text = f.ocr_result or qdrant_texts.get(f.id)
        if not text:
            continue
        out.append({"id": f.id, "filename": f.filename, "ocr_result": text})
        if len(out) >= min(max(limit, 1), 500):
            break
    return out