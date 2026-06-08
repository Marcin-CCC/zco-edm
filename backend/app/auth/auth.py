from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserRole
from app.schemas import UserCreate, UserInDB, UserUpdate
from app.auth.jwt_handler import hash_password, verify_password, create_access_token, get_current_user
from app.config import settings
from datetime import datetime
import os

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Rejestracja nowego uzytkownika. Tylko admin."""


@router.post("/register-setup", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def register_setup_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    """Initial setup registration - available only when no admin users exist.
    This endpoint allows creating the first admin account without authentication.
    """
    # Check if any admin user already exists
    existing_admins = db.query(User).filter(User.role == UserRole.ADMIN).all()
    if existing_admins:
        raise HTTPException(
            status_code=400,
            detail="Admin user already exists. Use /api/auth/register with admin token."
        )
    
    # Enforce admin role for setup
    if user_data.role != UserRole.ADMIN:
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
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Brak uprawnien")

    existing = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Uzytkownik z podanym emailem lub nazwa istnieje")

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
            detail="Brak danych logowania",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(
        (User.email == username) | (User.username == username)
    ).first()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidlowy email lub haslo",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Uzytkownik jest nieaktywny")

    user.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "is_admin": user.role == UserRole.ADMIN,
        "role": user.role.value,
        "is_active": user.is_active,
        "last_login": user.last_login.isoformat() if user.last_login else None
    }


@router.get("/me", response_model=UserInDB)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Pobranie danych aktualnie zalogowanego uzytkownika."""
    return current_user


@router.get("/users/check/{username}")
async def check_user(username: str, db: Session = Depends(get_db)):
    """Sprawdza czy uzytkownik istnieje."""
    user = db.query(User).filter(User.username == username).first()
    if user:
        return {"exists": True, "user_id": user.id, "email": user.email, "role": user.role.value}
    return {"exists": False}


@router.get("/users", response_model=list[UserInDB])
async def list_users(skip: int = 0, limit: int = 50, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista wszystkich uzytkownikow. Tylko admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Brak uprawnien")
    return db.query(User).offset(skip).limit(limit).all()


@router.get("/users/{user_id}", response_model=UserInDB)
async def get_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pobranie danych uzytkownika."""
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Brak uprawnien")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uzytkownik nie znaleziony")
    return user


@router.put("/users/{user_id}", response_model=UserInDB)
async def update_user(user_id: int, user_update: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Edycja uzytkownika. Tylko admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Brak uprawnien")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uzytkownik nie znaleziony")
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.username is not None:
        user.username = user_update.username
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.role is not None:
        user.role = user_update.role
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Usunięcie uzytkownika. Tylko admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Brak uprawnien")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uzytkownik nie znaleziony")
    db.delete(user)
    db.commit()