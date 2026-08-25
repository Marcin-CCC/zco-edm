"""Reguły słownika ról bez warstwy HTTP.

Osobny moduł, bo z tych funkcji korzysta też zarządzanie użytkownikami i folderami
(`app/auth/auth.py`, `app/folders/router.py`), a te nie mogą importować routera ról —
router importuje z nich zależność uwierzytelniania i powstałby cykl.
"""
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.messages import UserMessage
from app.models import Role

_POLISH_LETTERS = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
    "ó": "o", "ś": "s", "ź": "z", "ż": "z",
})
MAX_CODE_LENGTH = 50


def code_from_name(name: str) -> str:
    """„Pielęgniarka" → „PIELEGNIARKA". Pusty ciąg, gdy nazwa nie ma liter ani cyfr.

    Wielkie litery, bo takie kody zastaliśmy w bazie (SQLAlchemy zapisywał NAZWĘ
    elementu enuma). Jednolity zapis jest tu ważniejszy niż uroda: gdyby nowe role
    dostawały małe litery, uprawnienie nadane roli „nurse" nigdy nie dopasowałoby
    się do użytkownika z rolą „NURSE" — a taki błąd nie daje żadnego objawu poza
    tym, że komuś po cichu brakuje dostępu.
    """
    base = name.strip().lower().translate(_POLISH_LETTERS)
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return base.upper()[:MAX_CODE_LENGTH]


def unique_code(db: Session, name: str) -> str:
    """Kod z nazwy, a przy kolizji z sufiksem (`NURSE_2`).

    Dwie różne nazwy potrafią dać ten sam kod („Gość" i „gosc"), a kod musi być
    jednoznaczny — to on identyfikuje rolę w `users.role`.
    """
    base = code_from_name(name)
    if not base:
        raise HTTPException(status_code=400, detail=UserMessage("roles.nameNeedsChars"))
    code, n = base, 1
    while db.query(Role).filter(Role.code == code).first() is not None:
        n += 1
        suffix = f"_{n}"
        code = base[:MAX_CODE_LENGTH - len(suffix)] + suffix
    return code


def ensure_role_exists(db: Session, code: str) -> Role:
    """Rola o tym kodzie musi być w słowniku — inaczej 400.

    Do wersji 1.0.21 pilnował tego enum w warstwie pydantic. Po przejściu na słownik
    w bazie kontrola musi stać tutaj: bez niej literówka w kodzie roli zakłada
    użytkownika albo uprawnienie, którego nikt nigdy nie zobaczy w interfejsie.
    """
    role = db.query(Role).filter(Role.code == code).first()
    if role is None:
        raise HTTPException(status_code=400, detail=f"Rola „{code}” nie istnieje.")
    return role
