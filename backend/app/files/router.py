import os
import logging
import shutil
from datetime import datetime
from typing import List, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.models import File as FileModel, Folder, FolderPermission, User, DocumentStatus, UserRole
from app.schemas import FileResponse as FileResponseSchema, FileCreate, FileUpdate
from app.auth.auth import get_current_user
from app.config import settings
from app.spark_transfer import spark_transfer_enabled, transfer_to_spark, SPARK_SHARED_DIR
from app.rbac import readable_folder_ids, writable_folder_ids, can_read_file_folder

router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)


# ==================== HELPERS ====================
# Save files inside mounted Docker volume at /data/shared_docs
# This ensures files persist across container restarts AND are accessible by Docling
_DOCKER_SHARED = "/data/shared_docs"
# Project root is one level above backend/app (fallback for non-Docker dev)
_PROJECT_ROOT_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "shared_docs")
STORAGE_DIR = _DOCKER_SHARED if os.path.exists(_DOCKER_SHARED) else _PROJECT_ROOT_SHARED

# Publiczny adres backendu widziany z n8n (do callbacków statusu).
# Dev lokalny: http://<IP-PC-w-LAN>:8001, Spark: http://192.168.1.34:8083
BACKEND_CALLBACK_URL = os.getenv("BACKEND_CALLBACK_URL", "http://192.168.1.34:8083").rstrip("/")


def build_webhook_payload(file_id: int, file_path: str, folder_id: int | None = None) -> dict:
    """Zbuduj payload webhooka dla n8n z gotowym URL-em do aktualizacji statusu.

    `folder_id` trafia do payloadu Qdranta (Default Data Loader) i służy do
    filtrowania RBAC w czacie (Faza C). None = plik w katalogu głównym.
    """
    return {
        "file_id": file_id,
        "file_path": file_path,
        "folder_id": folder_id,
        "status_update_url": f"{BACKEND_CALLBACK_URL}/api/webhook/file/{file_id}/status",
    }


def get_mime_type(filename: str) -> str:
    """Determine MIME type from file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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

    # Generate storage path
    if folder_id:
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            logger.warning(f"[UPLOAD] Folder {folder_id} nie istnieje")
            raise HTTPException(status_code=404, detail="Folder nie istnieje.")
        relative_path = os.path.join(folder.path.lstrip("/"), file.filename)
    else:
        logger.debug("[UPLOAD] Brak folder_id — zapis do katalogu głównego")
        relative_path = file.filename
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
        filename=file.filename,
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

    files = query.order_by(FileModel.created_at.desc()).offset(skip).limit(limit).all()

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

    files = query.order_by(FileModel.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for f in files:
        folder_data = None
        if f.folder:
            folder_data = {"id": f.folder.id, "name": f.folder.name, "path": f.folder.path}
        
        uploader_data = None
        if f.uploader:
            uploader_data = {"id": f.uploader.id, "username": f.uploader.username, "email": f.uploader.email}
        
        # Powód błędu i czas parsowania zapisane w metadanych
        error_message = None
        processing_seconds = None
        if isinstance(f.metadata_, dict):
            error_message = f.metadata_.get("error")
            processing_seconds = f.metadata_.get("processing_seconds")

        result.append({
            "id": f.id,
            "document_id": None,  # File doesn't have document_id, keeping for compatibility
            "file_name": f.filename,
            "status": f.status.value if hasattr(f.status, 'value') else str(f.status),
            "page_count": 0,  # Files don't have page count yet
            "error_message": error_message,
            "processing_seconds": processing_seconds,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "started_at": None,
            "completed_at": None,
            "folder": folder_data,
            "uploader": uploader_data,
        })
    
    return result


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
    if current_user.role != UserRole.ADMIN:
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
    from app.qdrant_client import delete_vectors_by_file_id
    qdrant_result = delete_vectors_by_file_id(file_obj.id)

    # Delete physical file (lokalna kopia; plik na Sparku zostaje — dev mode)
    local_path = _resolve_local_path(file_obj.file_path)
    if os.path.exists(local_path):
        os.remove(local_path)

    # Delete DB record
    db.delete(file_obj)
    db.commit()

    return {"message": "Plik został usunięty.", "qdrant": qdrant_result}


@router.put("/{file_id}", response_model=FileResponseSchema)
def update_file(
    file_id: int,
    file_update: FileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update file metadata (status, folder). Admin only."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator może aktualizować pliki.")

    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    update_data = file_update.model_dump(exclude_unset=True)
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
            "status": f.status,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
            "folder": folder_data,
            "uploader": uploader_data,
        })

    return result

