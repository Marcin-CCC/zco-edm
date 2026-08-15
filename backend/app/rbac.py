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

from app.models import ROLE_ADMIN, Folder, FolderPermission, AccessLevel, Role, User


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
    if user.is_admin:
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
    if user.is_admin:
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
    """Zbiór id folderów WIDOCZNYCH w drzewie = dokładnie foldery czytelne.

    NIE dołączamy folderów nadrzędnych bez dostępu — inaczej użytkownik widziałby
    „pusty" folder-rodzic, do którego nie ma praw. Dozwolony podfolder z
    niedostępnym rodzicem jest przenoszony na najwyższy poziom w
    :func:`build_folder_tree` (parametr ``allowed_ids``). ``None`` = admin.
    """
    return readable_folder_ids(user, db)


def effective_permissions(folder_id: int, db: Session) -> list[dict]:
    """Efektywne uprawnienia folderu = suma uprawnień folderu i jego przodków
    (dziedziczenie po łańcuchu rodziców). Dla każdej roli zwraca najwyższy
    poziom dostępu (write > read).

    Używane m.in. do pokazania, jakie role odziedziczy NOWY podfolder danego
    folderu (jego efektywny zestaw = to, co dziedziczą dzieci).
    Zwraca listę: ``[{"role": "DOCTOR", "access_level": "write"}, ...]``.
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


def _rank(level) -> int:
    """Ranga poziomu dostępu: brak(0) < read(1) < write(2)."""
    if level is None:
        return 0
    v = level.value if hasattr(level, "value") else str(level)
    return 2 if v == "write" else 1 if v == "read" else 0


def access_overview(db: Session) -> dict:
    """Zestawienie dostępów dla wszystkich ról (poza adminem) — do audytu.

    Zwraca mapę ``role -> [ {folder_id, name, path, access_level, source} ]``,
    gdzie uwzględniony jest dostęp EFEKTYWNY (z dziedziczeniem po ścieżce):
    - ``access_level`` — efektywny poziom roli na folderze ("read"/"write"),
    - ``source`` — "direct" gdy poziom wynika z uprawnienia nadanego wprost na
      tym folderze (rozszerza ponad dziedziczone), "inherited" gdy z nadrzędnego.
    Rola bez żadnego dostępu ma pustą listę.
    """
    folders = db.query(Folder).all()
    by_id = {f.id: f for f in folders}
    perms = db.query(FolderPermission).all()

    direct: dict = {}  # folder_id -> {role: access_level}
    for p in perms:
        direct.setdefault(p.folder_id, {})[p.role] = p.access_level

    # Role bierzemy ze słownika w bazie, nie z listy w kodzie: administrator
    # zakłada własne. Admina pomijamy — ma pełny dostęp z definicji, więc jego
    # zestawienie zawsze byłoby spisem wszystkich folderów.
    roles = [
        r.code for r in db.query(Role).filter(Role.code != ROLE_ADMIN)
        .order_by(Role.sort_order, Role.name).all()
    ]
    result: dict = {code: [] for code in roles}

    for f in folders:
        # łańcuch przodków (bez samego f)
        ancestors: list[int] = []
        cur = by_id.get(f.parent_id) if f.parent_id is not None else None
        while cur is not None:
            ancestors.append(cur.id)
            cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None

        for role in roles:
            own = direct.get(f.id, {}).get(role)
            inh = None
            for aid in ancestors:
                lvl = direct.get(aid, {}).get(role)
                if lvl is not None and _rank(lvl) > _rank(inh):
                    inh = lvl
            if own is None and inh is None:
                continue
            eff = own if _rank(own) >= _rank(inh) else inh
            source = "direct" if (own is not None and _rank(own) > _rank(inh)) else "inherited"
            result[role].append({
                "folder_id": f.id,
                "name": f.name,
                "path": f.path,
                "access_level": eff.value if hasattr(eff, "value") else str(eff),
                "source": source,
            })

    for r in result:
        result[r].sort(key=lambda x: x["path"])
    return result


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
