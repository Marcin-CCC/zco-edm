"""
RBAC per folder-dziedzina (model rolowy).

Widoczność plików i folderów dla użytkownika NIE-admina wynika z uprawnień
przypisanych jego ROLI do folderów (tabela `folder_permissions`), z
dziedziczeniem po ścieżce: uprawnienie do `/X` obejmuje `/X` oraz wszystkie
podfoldery `/X/...`.

Zasady:
- ADMIN ma pełny dostęp — funkcje zwracają ``None`` (brak ograniczeń).
- Pliki w rootcie (``folder_id IS NULL``) są niesklasyfikowane → widoczne
  wyłącznie dla admina (nie da się do nich przypisać FolderPermission).
- Poziom ``read`` wystarcza do przeglądania; ``write`` implikuje ``read``.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Folder, FolderPermission, AccessLevel, User, UserRole


def _is_under(path: str, root: str) -> bool:
    """Czy ``path`` to ``root`` albo jego podfolder (dopasowanie po prefiksie ścieżki)."""
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def readable_folder_ids(user: User, db: Session) -> Optional[set[int]]:
    """Zbiór id folderów, których PLIKI użytkownik może czytać.

    Zwraca:
    - ``None`` — brak ograniczeń (admin),
    - ``set[int]`` — dozwolone id folderów (rola ma uprawnienie do folderu lub
      któregoś z jego przodków); pusty zbiór = brak dostępu do czegokolwiek.
    """
    if user.role == UserRole.ADMIN:
        return None

    perms = db.query(FolderPermission).filter(FolderPermission.role == user.role).all()
    if not perms:
        return set()

    permitted_ids = {p.folder_id for p in perms}
    all_folders = db.query(Folder).all()
    permitted_paths = [f.path for f in all_folders if f.id in permitted_ids]
    if not permitted_paths:
        return set()

    allowed: set[int] = set()
    for f in all_folders:
        if any(_is_under(f.path, pp) for pp in permitted_paths):
            allowed.add(f.id)
    return allowed


def writable_folder_ids(user: User, db: Session) -> Optional[set[int]]:
    """Zbiór id folderów, do których użytkownik może ZAPISYWAĆ (upload/usuwanie plików).

    Liczy tylko uprawnienia o poziomie ``write`` (z dziedziczeniem po ścieżce).
    ``None`` = admin (bez ograniczeń); pusty zbiór = brak prawa zapisu gdziekolwiek.
    """
    if user.role == UserRole.ADMIN:
        return None

    from app.models import AccessLevel
    perms = db.query(FolderPermission).filter(
        FolderPermission.role == user.role,
        FolderPermission.access_level == AccessLevel.WRITE,
    ).all()
    if not perms:
        return set()

    permitted_ids = {p.folder_id for p in perms}
    all_folders = db.query(Folder).all()
    permitted_paths = [f.path for f in all_folders if f.id in permitted_ids]
    if not permitted_paths:
        return set()

    allowed: set[int] = set()
    for f in all_folders:
        if any(_is_under(f.path, pp) for pp in permitted_paths):
            allowed.add(f.id)
    return allowed


def visible_folder_ids(user: User, db: Session) -> Optional[set[int]]:
    """Zbiór id folderów WIDOCZNYCH w drzewie: czytelne + ich przodkowie.

    Przodkowie są dołączani, aby dało się nawigować do dozwolonego podfolderu
    (same przodki nie odsłaniają swoich plików — to reguluje
    :func:`readable_folder_ids`). ``None`` = admin (wszystko widoczne).
    """
    readable = readable_folder_ids(user, db)
    if readable is None:
        return None
    if not readable:
        return set()

    by_id = {f.id: f for f in db.query(Folder).all()}
    visible = set(readable)
    for fid in list(readable):
        cur = by_id.get(fid)
        # wejdź w górę po przodkach
        while cur is not None and cur.parent_id is not None:
            visible.add(cur.parent_id)
            cur = by_id.get(cur.parent_id)
    return visible


def effective_permissions(folder_id: int, db: Session) -> list[dict]:
    """Efektywne uprawnienia folderu = suma uprawnień folderu i jego przodków
    (dziedziczenie po łańcuchu rodziców). Dla każdej roli zwraca najwyższy
    poziom dostępu (write > read).

    Używane m.in. do pokazania, jakie role odziedziczy NOWY podfolder danego
    folderu (jego efektywny zestaw = to, co dziedziczą dzieci).
    Zwraca listę: ``[{"role": "doctor", "access_level": "write"}, ...]``.
    """
    by_id = {f.id: f for f in db.query(Folder).all()}
    chain_ids: list[int] = []
    cur = by_id.get(folder_id)
    while cur is not None:
        chain_ids.append(cur.id)
        cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
    if not chain_ids:
        return []

    perms = (
        db.query(FolderPermission)
        .filter(FolderPermission.folder_id.in_(chain_ids))
        .all()
    )
    best: dict = {}
    for p in perms:
        if p.role not in best or p.access_level == AccessLevel.WRITE:
            best[p.role] = p.access_level

    def _val(x):
        return x.value if hasattr(x, "value") else str(x)

    return [{"role": _val(r), "access_level": _val(a)} for r, a in best.items()]


def can_read_file_folder(folder_id: Optional[int], readable: Optional[set[int]]) -> bool:
    """Czy plik w folderze ``folder_id`` jest czytelny przy danym zbiorze ``readable``.

    ``readable is None`` = admin (zawsze True). Plik w rootcie (``folder_id`` puste)
    jest czytelny tylko dla admina.
    """
    if readable is None:
        return True
    if folder_id is None:
        return False
    return folder_id in readable
