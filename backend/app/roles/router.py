"""Zarządzanie rolami użytkowników.

Rola to dane, nie kod: administrator zakłada własne role w interfejsie (podstrona
„Lista dostępów"), a wszystko, co w systemie zależy od roli — uprawnienia do
folderów, filtr RBAC, widoczność menu — czyta ten słownik.

Trzy zasady, które trzymają spójność:

1. `code` jest niezmienny. To on leży w `users.role` i `folder_permissions.role`
   jako zwykły tekst (bez klucza obcego — schemat powstaje przez `create_all`,
   które nie dokłada więzów do istniejących tabel). Zmiana kodu oznaczałaby
   przepisanie dwóch tabel w zamian za kosmetykę, więc edytowalna jest wyłącznie
   `name`, czyli etykieta w interfejsie.
2. Roli systemowej (ADMIN, GUEST) nie można usunąć. ADMIN jest wpisany w każdą
   kontrolę uprawnień, GUEST jest rolą domyślną nowego użytkownika.
3. Usunięcie roli kasuje jej uprawnienia do folderów w tej samej transakcji.
   Gdyby zostały, założenie później roli o tym samym kodzie po cichu odziedziczyłoby
   stare dostępy — to jedyne miejsce w tej funkcjonalności, gdzie da się zrobić
   dziurę w uprawnieniach.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.auth import get_current_user
from app.database import get_db
from app.models import FolderPermission, Role, User
from app.roles.service import ensure_role_exists, unique_code
from app.schemas import RoleCreate, RoleRename, RoleResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/roles", tags=["Roles"])

def _usage(db: Session) -> tuple[dict, dict]:
    """Ile użytkowników i ile uprawnień folderowych ma każdy kod roli."""
    users = dict(db.query(User.role, func.count(User.id)).group_by(User.role).all())
    perms = dict(
        db.query(FolderPermission.role, func.count(FolderPermission.id))
        .group_by(FolderPermission.role).all()
    )
    return users, perms


def _as_response(role: Role, users: dict, perms: dict) -> RoleResponse:
    return RoleResponse(
        code=role.code,
        name=role.name,
        is_system=role.is_system,
        sort_order=role.sort_order,
        users_count=users.get(role.code, 0),
        permissions_count=perms.get(role.code, 0),
    )


def _require_admin(current_user: User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zarządzać rolami.")


def _get_role(db: Session, code: str) -> Role:
    role = db.query(Role).filter(Role.code == code).first()
    if role is None:
        raise HTTPException(status_code=404, detail=f"Rola „{code}” nie istnieje.")
    return role


@router.get("", response_model=list[RoleResponse])
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Słownik ról wraz z liczbą użytkowników i uprawnień.

    Dostępne dla każdego zalogowanego: front potrzebuje etykiet ról (choćby po to,
    by pokazać własną rolę w profilu), a same nazwy ról nie są informacją wrażliwą.
    Zmieniać słownik może wyłącznie administrator.
    """
    users, perms = _usage(db)
    roles = db.query(Role).order_by(Role.sort_order, Role.name).all()
    return [_as_response(r, users, perms) for r in roles]


@router.post("", response_model=RoleResponse, status_code=201)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Nowa rola. Opcjonalnie z kopią uprawnień innej roli.

    Kopiowanie uprawnień jest tu nie dla wygody, tylko dlatego, że rola bez dostępu
    do żadnego folderu nic nie robi — bez tego administrator musiałby po utworzeniu
    roli przejść do modułu Pliki i nadać dostęp folder po folderze.
    """
    _require_admin(current_user)

    name = (payload.name or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Nazwa roli musi mieć co najmniej 2 znaki.")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Nazwa roli może mieć najwyżej 100 znaków.")

    istnieje = db.query(Role).filter(func.lower(Role.name) == name.lower()).first()
    if istnieje is not None:
        raise HTTPException(status_code=409, detail=f"Rola „{istnieje.name}” już istnieje.")

    ostatnia = db.query(func.max(Role.sort_order)).scalar() or 0
    role = Role(
        code=unique_code(db, name),
        name=name,
        is_system=False,
        sort_order=ostatnia + 10,
    )
    db.add(role)

    skopiowane = 0
    if payload.copy_permissions_from:
        zrodlo = _get_role(db, payload.copy_permissions_from)
        for p in db.query(FolderPermission).filter(FolderPermission.role == zrodlo.code).all():
            db.add(FolderPermission(
                folder_id=p.folder_id, role=role.code, access_level=p.access_level,
            ))
            skopiowane += 1

    db.commit()
    db.refresh(role)
    logger.info(
        "[ROLE] Utworzono %s (%s) przez %s; skopiowanych uprawnień: %d",
        role.code, role.name, current_user.username, skopiowane,
    )
    users, perms = _usage(db)
    return _as_response(role, users, perms)


@router.patch("/{code}", response_model=RoleResponse)
def rename_role(
    code: str,
    payload: RoleRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zmiana etykiety roli. Kod zostaje — patrz zasada 1 w nagłówku modułu.

    Rolę systemową też wolno przemianować: „Gość" na „Pracownik zewnętrzny" nie
    zmienia niczego w działaniu, bo kontrole uprawnień patrzą na kod.
    """
    _require_admin(current_user)
    role = _get_role(db, code)

    name = (payload.name or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Nazwa roli musi mieć co najmniej 2 znaki.")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Nazwa roli może mieć najwyżej 100 znaków.")

    kolizja = (
        db.query(Role)
        .filter(func.lower(Role.name) == name.lower(), Role.code != role.code)
        .first()
    )
    if kolizja is not None:
        raise HTTPException(status_code=409, detail=f"Rola „{kolizja.name}” już istnieje.")

    poprzednia, role.name = role.name, name
    db.commit()
    db.refresh(role)
    logger.info("[ROLE] %s: „%s” → „%s” (przez %s)",
                role.code, poprzednia, role.name, current_user.username)
    users, perms = _usage(db)
    return _as_response(role, users, perms)


@router.delete("/{code}")
def delete_role(
    code: str,
    reassign_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuwa rolę; użytkowników przenosi do `reassign_to`, uprawnienia kasuje.

    Bez `reassign_to` operacja jest odrzucana, gdy rolę ktoś ma przypisaną —
    interfejs pokazuje wtedy liczby i pyta, dokąd przenieść tych ludzi. Cichy
    przydział do roli domyślnej byłby gorszy: administrator dowiedziałby się
    o zmianie uprawnień swoich użytkowników dopiero z ich zgłoszeń.
    """
    _require_admin(current_user)
    role = _get_role(db, code)

    if role.is_system:
        raise HTTPException(
            status_code=400,
            detail=f"Rola „{role.name}” jest systemowa i nie może zostać usunięta.",
        )

    users_count = db.query(User).filter(User.role == role.code).count()
    if users_count and not reassign_to:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Rolę „{role.name}” ma przypisanych {users_count} użytkowników. "
                "Wskaż rolę, do której mają zostać przeniesieni."
            ),
        )

    target = None
    if reassign_to:
        target = _get_role(db, reassign_to)
        if target.code == role.code:
            raise HTTPException(
                status_code=400,
                detail="Nie można przenieść użytkowników do roli, która jest usuwana.",
            )

    if target is not None and users_count:
        db.query(User).filter(User.role == role.code).update(
            {User.role: target.code}, synchronize_session=False,
        )

    perms_removed = (
        db.query(FolderPermission)
        .filter(FolderPermission.role == role.code)
        .delete(synchronize_session=False)
    )
    db.delete(role)
    db.commit()

    logger.info(
        "[ROLE] Usunięto %s przez %s; przeniesionych użytkowników: %d → %s; "
        "skasowanych uprawnień: %d",
        role.code, current_user.username, users_count if target else 0,
        target.code if target else "-", perms_removed,
    )
    return {
        "deleted": code,
        "users_moved": users_count if target else 0,
        "moved_to": target.code if target else None,
        "permissions_removed": perms_removed,
    }
