import logging
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.database import get_db
from app.models import Folder, FolderPermission, File as FileModel, User
from app.roles.service import ensure_role_exists
from app.schemas import FolderResponse, FolderCreate, FolderPermissionResponse, FolderPermissionBase, FolderPermissionCreate, FolderTreeResponse
from datetime import datetime
from app.auth.auth import get_current_user
from app.rbac import visible_folder_ids, writable_folder_ids, effective_permissions, access_overview

router = APIRouter(prefix="/folders", tags=["Folders"])
logger = logging.getLogger(__name__)


def build_folder_tree(
    folders: List[Folder],
    parent_id: Optional[int] = None,
    writable: Optional[set] = None,
    file_counts: Optional[dict] = None,
    allowed_ids: Optional[set] = None,
) -> List[FolderTreeResponse]:
    """Build hierarchical folder tree.

    ``writable`` = zbiór id folderów zapisywalnych dla bieżącego użytkownika
    (``None`` = admin → zapis wszędzie).
    ``file_counts`` = mapa folder_id → liczba plików bezpośrednio w folderze.
    ``allowed_ids`` = zbiór id folderów widocznych dla użytkownika (``None`` =
    admin). Gdy rodzic folderu NIE jest w tym zbiorze, folder jest przenoszony na
    najwyższy poziom (efektywny rodzic = None), by nie pokazywać niedostępnego
    folderu-rodzica.
    """
    file_counts = file_counts or {}
    tree = []
    for folder in folders:
        eff_parent = folder.parent_id
        if allowed_ids is not None and eff_parent is not None and eff_parent not in allowed_ids:
            eff_parent = None  # rodzic niewidoczny → traktuj jako folder najwyższego poziomu
        if eff_parent == parent_id:
            children = build_folder_tree(folders, folder.id, writable, file_counts, allowed_ids)
            tree.append(FolderTreeResponse(
                id=folder.id,
                name=folder.name,
                path=folder.path,
                parent_id=eff_parent,
                description=folder.description,
                created_by=folder.created_by,
                created_at=folder.created_at,
                updated_at=folder.updated_at,
                can_write=(writable is None) or (folder.id in writable),
                file_count=file_counts.get(folder.id, 0),
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
    if not current_user.is_admin:
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
    # RBAC: nie-admin widzi tylko foldery dozwolone dla jego roli + ich przodków
    # (żeby dało się nawigować do dozwolonego podfolderu).
    visible = visible_folder_ids(current_user, db)
    if visible is not None:
        folders = [f for f in folders if f.id in visible]
    writable = writable_folder_ids(current_user, db)
    file_counts = dict(
        db.query(FileModel.folder_id, func.count(FileModel.id))
        .filter(FileModel.folder_id.isnot(None))
        .group_by(FileModel.folder_id)
        .all()
    )
    return build_folder_tree(folders, writable=writable, file_counts=file_counts, allowed_ids=visible)


@router.get("/access-overview")
def get_access_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zestawienie dostępów per rola (audyt). Tylko admin.

    Trasa MUSI być przed '/{folder_id}', inaczej złapałby ją parametr int.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może przeglądać listę dostępów.")
    return access_overview(db)


@router.get("/", response_model=List[FolderResponse])
def list_folders(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all folders."""
    visible = visible_folder_ids(current_user, db)
    query = db.query(Folder)
    if visible is not None:
        if not visible:
            return []
        query = query.filter(Folder.id.in_(visible))
    folders = query.offset(skip).limit(limit).all()
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
    # RBAC: nie-admin widzi tylko dozwolone foldery (+ przodków dla nawigacji).
    visible = visible_folder_ids(current_user, db)
    if visible is not None and folder_id not in visible:
        raise HTTPException(status_code=403, detail="Brak dostępu do tego folderu.")
    return folder


class FolderRename(BaseModel):
    name: str


@router.patch("/{folder_id}", response_model=FolderResponse)
def rename_folder(
    folder_id: int,
    payload: FolderRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zmień nazwę folderu (tylko admin) wraz ze ścieżkami całego poddrzewa.

    `Folder.path` jest wyliczoną ścieżką („/Rodzic/Dziecko"), a uprawnienia dziedziczą
    się po PREFIKSIE ścieżki (rbac._is_under). Dlatego zmiana nazwy musi przebudować
    ścieżki folderu ORAZ wszystkich podfolderów w JEDNEJ transakcji — niekompletna
    aktualizacja po cichu zepsułaby dostęp do dokumentów.

    Nie rusza dysku: przynależność pliku do folderu jest informacją w bazie
    (`files.folder_id`), a fizyczna ścieżka pliku jest od niej niezależna.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zmieniać nazwę folderu.")

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    new_name = (payload.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Nazwa nie może być pusta.")
    if "/" in new_name:
        raise HTTPException(status_code=400, detail="Nazwa nie może zawierać ukośnika.")
    if new_name == folder.name:
        return folder

    # Nowa ścieżka = ścieżka rodzica + nowa nazwa
    parent_path = ""
    if folder.parent_id:
        parent = db.query(Folder).filter(Folder.id == folder.parent_id).first()
        parent_path = parent.path if parent else ""
    new_path = f"{parent_path}/{new_name}"

    # Kolizja z rodzeństwem (ta sama zasada co przy tworzeniu folderu)
    collision = (
        db.query(Folder)
        .filter(Folder.path == new_path, Folder.id != folder.id)
        .first()
    )
    if collision:
        raise HTTPException(
            status_code=400,
            detail=f"Folder o nazwie {new_name} już istnieje w tym miejscu.",
        )

    old_path = folder.path
    # Poddrzewo: sam folder + wszystko, co leży pod jego ścieżką
    descendants = (
        db.query(Folder)
        .filter(Folder.path.like(f"{old_path}/%"))
        .all()
    )

    folder.name = new_name
    folder.path = new_path
    for d in descendants:
        d.path = new_path + d.path[len(old_path):]
    db.commit()
    db.refresh(folder)

    logger.info(
        f"[FOLDER-RENAME] {old_path!r} → {new_path!r} "
        f"(podfolderów: {len(descendants)}) przez {current_user.username}"
    )
    return folder


@router.delete("/{folder_id}", status_code=204)
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a folder (admin only)."""
    if not current_user.is_admin:
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
    perm_data: FolderPermissionBase,  # folder_id bierzemy ze ścieżki, nie z ciała
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ustaw uprawnienie roli na folderze (admin). Upsert: gdy rola ma już
    uprawnienie na tym folderze, podmienia poziom zamiast zwracać błąd."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może ustawiać uprawnienia.")

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")

    ensure_role_exists(db, perm_data.role)

    existing = db.query(FolderPermission).filter(
        FolderPermission.folder_id == folder_id,
        FolderPermission.role == perm_data.role,
    ).first()

    if existing:
        # Podmiana poziomu (np. Odczyt → Zapis) — intuicyjna zmiana z tego samego okna
        existing.access_level = perm_data.access_level
        db.commit()
        db.refresh(existing)
        return existing

    new_perm = FolderPermission(
        folder_id=folder_id,
        role=perm_data.role,
        access_level=perm_data.access_level,
    )
    db.add(new_perm)
    db.commit()
    db.refresh(new_perm)
    return new_perm


@router.get("/{folder_id}/effective-permissions")
def get_effective_permissions(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Efektywne uprawnienia folderu (własne + odziedziczone po przodkach).

    Służy do pokazania w popupie 'Nowy folder', jakie role odziedziczy nowy
    podfolder tego folderu. Tylko admin (jak pozostałe zarządzanie uprawnieniami).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zarządzać uprawnieniami.")
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder nie istnieje.")
    return effective_permissions(folder_id, db)


@router.get("/{folder_id}/permissions", response_model=List[FolderPermissionResponse])
def list_folder_permissions(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List permissions for a folder (admin only)."""
    if not current_user.is_admin:
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
    if not current_user.is_admin:
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