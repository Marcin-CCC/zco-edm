import os
import shutil
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.models import File as FileModel, Folder, FolderPermission, User, DocumentStatus, UserRole
from app.schemas import FileResponse as FileResponseSchema, FileCreate, FileUpdate
from app.auth.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["Files"])


# ==================== HELPERS ====================
# Use /data for Docker (mounted volume) or shared_docs relative to project root
# Try /data first (Docker), then project root shared_docs
_DOCKER_SHARED = "/data"
# Project root is one level above backend/app
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
    folder_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
            raise HTTPException(status_code=404, detail="Folder nie istnieje.")
        storage_path = os.path.join(STORAGE_DIR, folder.path.lstrip("/"), file.filename)
    else:
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

    db.refresh(db_file)

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
    """List files with optional filters."""
    query = db.query(FileModel).filter(FileModel.uploaded_by == current_user.id or current_user.role == UserRole.ADMIN)

    if folder_id is not None:
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