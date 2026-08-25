from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.messages import UserMessage
from app.database import get_db
from app.models import ROLE_ADMIN, User
from app.roles.service import ensure_role_exists
from app.locales import SUPPORTED_LOCALES, normalize_locale
from app.schemas import PasswordChange, ProfileUpdate, UserCreate, UserInDB, UserUpdate
from app.auth.jwt_handler import hash_password, verify_password, create_access_token, get_current_user
from app.config import settings
from datetime import datetime
import logging
import os
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Rejestracja nowego uzytkownika. Tylko admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail=UserMessage("common.noPermission"))

    existing = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=UserMessage("auth.userExists"))

    ensure_role_exists(db, user_data.role)

    new_user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        role=user_data.role,
        hashed_password=hash_password(user_data.password),
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/register-setup", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def register_setup_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    """Initial setup registration - available only when no admin users exist.
    This endpoint allows creating the first admin account without authentication.
    """
    # Check if any admin user already exists
    existing_admins = db.query(User).filter(User.role == ROLE_ADMIN).all()
    if existing_admins:
        raise HTTPException(
            status_code=400,
            detail="Admin user already exists. Use /api/auth/register with admin token."
        )
    
    # Enforce admin role for setup.
    # UWAGA: `user_data` to schemat pydantic, a nie model User — nie ma własności
    # `is_admin`, więc porównujemy kod roli wprost.
    if user_data.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=400,
            detail="Setup registration must create an admin user."
        )
    
    # Check for existing user
    existing = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="User with this email or username already exists"
        )
    
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        role=user_data.role,
        hashed_password=hash_password(user_data.password),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    """Logowanie uzytkownika i zwracanie tokenu JWT."""
    content_type = request.headers.get("content-type", "")
    username = ""
    password = ""

    try:
        if "application/json" in content_type:
            body = await request.json()
            username = body.get("email") or body.get("username", "")
            password = body.get("password", "")
        else:
            from urllib.parse import parse_qs
            body_bytes = await request.body()
            body_str = body_bytes.decode("utf-8")
            parsed = parse_qs(body_str)
            username = parsed.get("username", [""])[0]
            password = parsed.get("password", [""])[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nieprawidlowy format danych: {str(e)}"
        )

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UserMessage("auth.noCredentials"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Logowanie WYŁĄCZNIE adresem e-mail. Wcześniej działała też nazwa użytkownika,
    # przez co jeden napis mógł pasować do dwóch kont (nazwa jednego = e-mail
    # drugiego) i właściciel adresu tracił dostęp. Nazwa użytkownika jest teraz
    # tylko etykietą pokazywaną w interfejsie, więc jej zmiana nikomu nie szkodzi.
    # Porównanie bez rozróżniania wielkości liter — adresy e-mail są nieczułe na nią.
    user = db.query(User).filter(func.lower(User.email) == username.strip().lower()).first()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UserMessage("auth.badCredentials"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail=UserMessage("auth.inactive"))

    user.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "role": user.role,
        "is_active": user.is_active,
        "locale": user.locale,
        "last_login": user.last_login.isoformat() if user.last_login else None
    }


@router.get("/me", response_model=UserInDB)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Pobranie danych aktualnie zalogowanego uzytkownika."""
    return current_user


MIN_DLUGOSC_HASLA = 8
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def identyfikator_zajety(db: Session, wartosc: str, wlasne_id: int) -> bool:
    """Czy napis jest już czyimś loginem — w KTÓREJKOLWIEK z dwóch kolumn.

    Logowanie dopuszcza jedno i drugie (`email == x OR username == x`), więc
    unikalność wewnątrz jednej kolumny nie wystarcza. Bez tego sprawdzenia można
    ustawić sobie nazwę użytkownika równą CUDZEMU adresowi e-mail — zapytanie
    logujące zwraca wtedy pierwsze pasujące konto i właściciel adresu przestaje
    się logować (zmierzone: ofiara dostawała 401).
    """
    return db.query(User).filter(
        User.id != wlasne_id,
        (func.lower(User.username) == wartosc.lower()) | (func.lower(User.email) == wartosc.lower()),
    ).first() is not None


@router.patch("/me", response_model=UserInDB)
async def update_own_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zmiana WŁASNYCH danych konta (strona Profil).

    Rola i status pozostają poza zasięgiem użytkownika — zmienia je tylko admin
    przez `PUT /users/{id}`. Login i e-mail muszą pozostać unikalne, bo służą do
    logowania; kolizję zgłaszamy komunikatem, a nie błędem bazy.
    """
    zmiany: list[str] = []

    if payload.username is not None:
        # Spacje są dozwolone: logowanie odbywa się ADRESEM E-MAIL, a nazwa
        # użytkownika jest etykietą pokazywaną w interfejsie — w bazie są już konta
        # w rodzaju „Paweł C" i zakaz spacji uniemożliwiłby im zapis własnych danych.
        nowa = payload.username.strip()
        if len(nowa) < 3:
            raise HTTPException(status_code=400, detail=UserMessage("auth.usernameTooShort"))
        if len(nowa) > 100:
            raise HTTPException(status_code=400, detail=UserMessage("auth.usernameTooLong"))
        if nowa != current_user.username:
            if identyfikator_zajety(db, nowa, current_user.id):
                raise HTTPException(status_code=409, detail=UserMessage("auth.usernameTaken"))
            current_user.username = nowa
            zmiany.append("username")

    if payload.email is not None:
        nowy = payload.email.strip()
        if not _EMAIL_RE.match(nowy):
            raise HTTPException(status_code=400, detail=UserMessage("auth.badEmail"))
        if nowy.lower() != (current_user.email or "").lower():
            if identyfikator_zajety(db, nowy, current_user.id):
                raise HTTPException(status_code=409, detail=UserMessage("auth.emailTaken"))
            current_user.email = nowy
            zmiany.append("email")

    if payload.full_name is not None:
        nowe = payload.full_name.strip()
        if len(nowe) > 200:
            raise HTTPException(status_code=400, detail=UserMessage("auth.fullNameTooLong"))
        if (nowe or None) != current_user.full_name:
            current_user.full_name = nowe or None
            zmiany.append("full_name")

    if payload.locale is not None:
        # Pusty napis = powrót do domyślnego języka wdrożenia, dlatego NULL, nie "".
        # Nierozpoznany kod odrzucamy: kolumna wskazuje katalog tłumaczeń i wpis bez
        # katalogu zostawiłby użytkownika z interfejsem, którego nie ma czym wypełnić.
        nowy = normalize_locale(payload.locale) if payload.locale.strip() else None
        if payload.locale.strip() and nowy is None:
            raise HTTPException(
                status_code=400,
                detail=UserMessage("auth.unsupportedLocale", lista=", ".join(SUPPORTED_LOCALES)),
            )
        if nowy != current_user.locale:
            current_user.locale = nowy
            zmiany.append("locale")

    if zmiany:
        db.commit()
        db.refresh(current_user)
        logger.info(f"[PROFIL] {current_user.username} zmienił: {', '.join(zmiany)}")
    return current_user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zmiana własnego hasła — wymaga podania aktualnego.

    Sesja jest kluczowana po `id` użytkownika, więc token po zmianie hasła nadal
    działa. Frontend celowo wylogowuje po sukcesie, żeby użytkownik od razu
    sprawdził nowe hasło (decyzja produktowa).
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail=UserMessage("auth.wrongCurrentPassword"))
    nowe = payload.new_password or ""
    if len(nowe) < MIN_DLUGOSC_HASLA:
        raise HTTPException(
            status_code=400,
            detail=UserMessage("auth.passwordTooShort", min=MIN_DLUGOSC_HASLA),
        )
    if verify_password(nowe, current_user.hashed_password):
        raise HTTPException(status_code=400, detail=UserMessage("auth.samePassword"))

    current_user.hashed_password = hash_password(nowe)
    db.commit()
    logger.info(f"[PROFIL] {current_user.username} zmienił hasło")


@router.get("/users/check/{username}")
async def check_user(username: str, db: Session = Depends(get_db)):
    """Sprawdza czy uzytkownik istnieje."""
    user = db.query(User).filter(User.username == username).first()
    if user:
        return {"exists": True, "user_id": user.id, "email": user.email, "role": user.role}
    return {"exists": False}


@router.get("/users", response_model=list[UserInDB])
async def list_users(skip: int = 0, limit: int = 50, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista wszystkich uzytkownikow. Tylko admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail=UserMessage("common.noPermission"))
    return db.query(User).offset(skip).limit(limit).all()


@router.get("/users/{user_id}", response_model=UserInDB)
async def get_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pobranie danych uzytkownika."""
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail=UserMessage("common.noPermission"))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=UserMessage("common.userNotFound"))
    return user


@router.put("/users/{user_id}", response_model=UserInDB)
async def update_user(user_id: int, user_update: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Edycja uzytkownika. Tylko admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail=UserMessage("common.noPermission"))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=UserMessage("common.userNotFound"))
    # Login sprawdza obie kolumny naraz, więc kolizja MIĘDZY nimi odcięłaby komuś
    # dostęp — admin też nie powinien móc jej wprowadzić przez pomyłkę.
    if user_update.email is not None and identyfikator_zajety(db, user_update.email, user.id):
        raise HTTPException(status_code=409, detail=UserMessage("auth.emailTakenByOther"))
    if user_update.username is not None and identyfikator_zajety(db, user_update.username, user.id):
        raise HTTPException(status_code=409, detail=UserMessage("auth.usernameTakenByOther"))
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.username is not None:
        user.username = user_update.username
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.role is not None:
        ensure_role_exists(db, user_update.role)
        user.role = user_update.role
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    # Zmiana hasła — tylko gdy podane niepuste (puste = pozostaw bez zmian)
    if user_update.password:
        user.hashed_password = hash_password(user_update.password)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Usunięcie uzytkownika. Tylko admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail=UserMessage("common.noPermission"))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=UserMessage("common.userNotFound"))
    db.delete(user)
    db.commit()