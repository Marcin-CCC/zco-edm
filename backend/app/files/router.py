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

router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)


# ==================== HELPERS ====================
# Save files inside mounted Docker volume at /data/shared_docs
# This ensures files persist across container restarts AND are accessible by Docling
_DOCKER_SHARED = "/data/shared_docs"
# Project root is one level above backend/app (fallback for non-Docker dev)
_PROJECT_ROOT_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "shared_docs")
STORAGE_DIR = _DOCKER_SHARED if os.path.exists(_DOCKER_SHARED) else _PROJECT_ROOT_SHARED


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
    print(f"[UPLOAD DEBUG] received folder_id={folder_id}, filename={file.filename}")
    """Upload a file (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator może wgrywać pliki.")

    # Read file content for size check
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB
        raise HTTPException(status_code=413, detail="Plik jest za duży. Maksymalny rozmiar to 100MB.")

    # Reset file position for later reading
    file.file.seek(0)

    # Validate file type
    allowed_extensions = {"pdf", "docx", "xlsx", "pptx"}
    ext = get_extension(file.filename)
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Nieobsługiwany typ pliku. Dozwolone: {', '.join(sorted(allowed_extensions))}")

    # Generate storage path
    if folder_id:
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            print(f"[UPLOAD DEBUG] Folder not found for id={folder_id}")
            raise HTTPException(status_code=404, detail="Folder nie istnieje.")
        storage_path = os.path.join(STORAGE_DIR, folder.path.lstrip("/"), file.filename)
    else:
        print(f"[UPLOAD DEBUG] No folder_id, saving to root")
        storage_path = os.path.join(STORAGE_DIR, file.filename)

    os.makedirs(os.path.dirname(storage_path) or STORAGE_DIR, exist_ok=True)

    # Save file - write the content we already read
    with open(storage_path, "wb") as buffer:
        buffer.write(content)

    # Get file size
    file_size = os.path.getsize(storage_path)

    # Create DB record
    db_file = FileModel(
        filename=file.filename,
        file_path=storage_path,
        mime_type=get_mime_type(file.filename),
        size=file_size,
        folder_id=folder_id,
        uploaded_by=current_user.id,
        status=DocumentStatus.PENDING,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # >>> Trigger n8n webhook about new file <<<
    webhook_success = False
    webhook_error = None
    try:
        # Load cache from DB to get the correct webhook URL
        from app.settings.router import _load_cache_from_db, get_webhook_url
        _load_cache_from_db(db)
        webhook_url = get_webhook_url()
        logger.info(f"[UPLOAD] Webhook URL for file {db_file.id}: {webhook_url}")
        
        # Use anyio.run for synchronous async execution (same pattern as retry)
        import anyio
        async def call_webhook():
            nonlocal webhook_success, webhook_error
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        webhook_url,
                        json={"file_path": db_file.file_path, "file_id": db_file.id},
                    )
                    if resp.status_code == 200:
                        webhook_success = True
                        logger.info(f"[UPLOAD] Webhook called successfully for file {db_file.id}")
                    else:
                        webhook_error = f"Webhook returned status {resp.status_code}: {resp.text}"
                        logger.warning(f"[UPLOAD] Webhook error for file {db_file.id}: {webhook_error}")
            except Exception as e:
                webhook_error = str(e)
                logger.error(f"[UPLOAD] Failed to call webhook for file {db_file.id}: {str(e)}")
        anyio.run(call_webhook)
    except Exception as e:
        webhook_error = str(e)
        logger.error(f"[UPLOAD] Webhook failed for file {db_file.id}: {webhook_error}")
    
    # Set file status to ERROR if webhook failed
    if not webhook_success:
        db_file.status = DocumentStatus.ERROR
        db.commit()
        db.refresh(db_file)
        logger.error(f"[UPLOAD] File {db_file.id} ({db_file.filename}) status set to ERROR: {webhook_error}")
    # <<< END n8n trigger >>>

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
    query = db.query(FileModel).filter(FileModel.uploaded_by == current_user.id or current_user.role == UserRole.ADMIN)

    if folder_id is None:
        # No folder_id specified - show only root files (folder_id IS NULL)
        query = query.filter(FileModel.folder_id == None)
    elif folder_id == 0:
        # folder_id=0 is special - show all files (legacy behavior)
        pass  # No filter applied
    else:
        # Specific folder - show files in that folder
        query = query.filter(FileModel.folder_id == folder_id)
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
    query = db.query(FileModel).filter(
        FileModel.uploaded_by == current_user.id or current_user.role == UserRole.ADMIN
    )
    
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
        
        result.append({
            "id": f.id,
            "document_id": None,  # File doesn't have document_id, keeping for compatibility
            "file_name": f.filename,
            "status": f.status.value if hasattr(f.status, 'value') else str(f.status),
            "page_count": 0,  # Files don't have page count yet
            "error_message": None,
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
    query = db.query(FileModel).filter(
        FileModel.uploaded_by == current_user.id or current_user.role == UserRole.ADMIN
    )
    
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

    # Check access - user must have read access to the folder or be admin
    if file_obj.folder_id:
        folder_perm = db.query(FolderPermission).filter(
            FolderPermission.folder_id == file_obj.folder_id,
            FolderPermission.role == current_user.role,
            FolderPermission.access_level == "read"
        ).first()
        if not folder_perm and current_user.role != UserRole.ADMIN:
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


@router.get("/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download a file."""
    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    if not os.path.exists(file_obj.file_path):
        raise HTTPException(status_code=404, detail="Plik nie istnieje na dysku.")

    return FileResponse(
        path=file_obj.file_path,
        filename=file_obj.filename,
        media_type=file_obj.mime_type or "application/octet-stream",
    )


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a file (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator może usuwać pliki.")

    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    # Delete physical file
    if os.path.exists(file_obj.file_path):
        os.remove(file_obj.file_path)

    # Delete DB record
    db.delete(file_obj)
    db.commit()

    return {"message": "Plik został usunięty."}


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
    mime_types = db.query(FileModel.mime_type).distinct().all()
    categories = []
    for (mt,) in mime_types:
        ext = mt.split("/")[-1] if mt else ""
        categories.append({
            "mime_type": mt,
            "extension": ext,
            "icon": get_file_icon(f"file.{ext}"),
            "count": db.query(FileModel).filter(FileModel.mime_type == mt).count(),
        })
    return categories


@router.get("/folder/{folder_id}/files", response_model=List[FileResponseSchema])
def list_folder_files(folder_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get files in a specific folder."""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

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

