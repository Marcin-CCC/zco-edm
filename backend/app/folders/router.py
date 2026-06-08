import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models import Folder, FolderPermission, User, UserRole
from app.schemas import FolderResponse, FolderCreate, FolderPermissionResponse, FolderPermissionCreate, FolderTreeResponse
from datetime import datetime
from app.auth.auth import get_current_user

router = APIRouter(prefix="/folders", tags=["Folders"])


def build_folder_tree(folders: List[Folder], parent_id: Optional[int] = None) -> List[FolderTreeResponse]:
    """Build hierarchical folder tree."""
    tree = []
    for folder in folders:
        if folder.parent_id == parent_id:
            children = build_folder_tree(folders, folder.id)
            tree.append(FolderTreeResponse(
                id=folder.id,
                name=folder.name,
                path=folder.path,
                parent_id=folder.parent_id,
                description=folder.description,
                created_by=folder.created_by,
                created_at=folder.created_at,
                updated_at=folder.updated_at,
                children=children,
            ))
    return tree


@router.post("/", response_model=FolderResponse)
def create_folder(
    folder_data: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new folder (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator moze tworzyc foldery.")

    # Check if folder with same path already exists
    full_path = f"/{folder_data.name}"
    if folder_data.parent_id:
        parent = db.query(Folder).filter(Folder.id == folder_data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found.")
        full_path = f"{parent.path}/{folder_data.name}"

    existing = db.query(Folder).filter(Folder.path == full_path).first()
    if existing:
        raise HTTPException(status_code=400, detail="Folder o podanej nazwie juz istnieje.")

    new_folder = Folder(
        name=folder_data.name,
        path=full_path,
        parent_id=folder_data.parent_id,
        created_by=current_user.id,
    )
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)

    return new_folder


@router.get("/tree", response_model=List[FolderTreeResponse])
def get_folder_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get hierarchical folder tree."""
    folders = db.query(Folder).all()
    return build_folder_tree(folders)


@router.get("/", response_model=List[FolderResponse])
def list_folders(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all folders."""
    folders = db.query(Folder).offset(skip).limit(limit).all()
    return folders


@router.get("/{folder_id}", response_model=FolderResponse)
def get_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get folder by ID."""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")
    return folder


@router.delete("/{folder_id}", status_code=204)
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a folder (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator moze usuwac foldery.")

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    # Delete associated permissions
    db.query(FolderPermission).filter(FolderPermission.folder_id == folder_id).delete()

    # Delete the folder (files will be handled by cascade or orphan)
    db.delete(folder)
    db.commit()
    return None


# ==================== Folder Permissions ====================

@router.post("/{folder_id}/permissions", response_model=FolderPermissionResponse)
def add_folder_permission(
    folder_id: int,
    perm_data: FolderPermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add permission to a folder (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator może ustawiać uprawnienia.")

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    existing = db.query(FolderPermission).filter(
        FolderPermission.folder_id == folder_id,
        FolderPermission.role == perm_data.role,
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Uprawnienie dla tej roli juz istnieje.")

    new_perm = FolderPermission(
        folder_id=folder_id,
        role=perm_data.role,
        access_level=perm_data.access_level,
    )
    db.add(new_perm)
    db.commit()
    db.refresh(new_perm)
    return new_perm


@router.get("/{folder_id}/permissions", response_model=List[FolderPermissionResponse])
def list_folder_permissions(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List permissions for a folder (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator może zarządzać uprawnieniami.")

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    permissions = db.query(FolderPermission).filter(FolderPermission.folder_id == folder_id).all()
    return permissions


@router.delete("/{folder_id}/permissions/{perm_id}", status_code=204)
def delete_folder_permission(
    folder_id: int,
    perm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a folder permission (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator może usuwać uprawnienia.")

    perm = db.query(FolderPermission).filter(
        FolderPermission.id == perm_id,
        FolderPermission.folder_id == folder_id,
    ).first()
    if not perm:
        raise HTTPException(status_code=404, detail="Uprawnienie nie istnieje.")

    db.delete(perm)
    db.commit()
    return None