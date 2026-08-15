import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import User, Setting
from app.schemas import SettingsResponse, SettingsUpdate
from app.config import settings as app_settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])

# In-memory cache for settings
_settings_cache: dict = {}
_cache_loaded = False


def _load_cache_from_db(db: Session) -> None:
    """Load settings from database into memory cache."""
    global _settings_cache, _cache_loaded
    records = db.query(Setting).all()
    _settings_cache = {r.key: r.value for r in records}
    _cache_loaded = True


def _save_cache_to_db(db: Session) -> None:
    """Save cached settings to database."""
    global _settings_cache
    for key, value in _settings_cache.items():
        existing = db.query(Setting).filter(Setting.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()


def get_webhook_url() -> str:
    """Get webhook URL from cache/DB, fallback to env settings."""
    url = _settings_cache.get("n8n_webhook_url")
    if url:
        return url
    return app_settings.N8N_WEBHOOK_URL


def get_chat_webhook_url() -> str | None:
    """Get chat webhook URL (n8n Chat Trigger) from cache/DB."""
    return _settings_cache.get("chat_webhook_url") or None


# Domyślne rozszerzenia = te, które realnie obsługuje workflow n8n
# (Switch on file ext: pdf/docx/xlsx/odt). pptx NIE ma gałęzi — celowo poza listą.
# odt idzie gałęzią tekstową: konwersja do DOCX (usługa 8084 /convert-to-docx),
# a dalej tym samym Doclingiem co docx — PDF jako półprodukt gubiłby tabele.
_DEFAULT_ALLOWED_EXTENSIONS = "pdf,docx,xlsx,odt"


def _parse_extensions(raw: str) -> list[str]:
    """Znormalizuj listę rozszerzeń: lowercase, bez kropki, bez pustych."""
    return [e.strip().lower().lstrip(".") for e in (raw or "").split(",") if e.strip()]


def get_allowed_extensions() -> set[str]:
    """Zbiór dozwolonych rozszerzeń plików z ustawień (fallback: domyślne).

    Uwaga: wołający powinien wcześniej wykonać _load_cache_from_db(db),
    tak jak przy get_webhook_url().
    """
    raw = _settings_cache.get("allowed_extensions") or _DEFAULT_ALLOWED_EXTENSIONS
    return set(_parse_extensions(raw))


# Auto-wylogowanie po bezczynności (minuty) — egzekwowane po stronie frontendu.
_DEFAULT_IDLE_TIMEOUT = 15
_MIN_IDLE_TIMEOUT = 1
_MAX_IDLE_TIMEOUT = 1440  # 24h


def get_idle_timeout() -> int:
    """Czas bezczynności do auto-wylogowania (minuty) z ustawień; fallback: domyślny."""
    raw = _settings_cache.get("idle_timeout_minutes")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_IDLE_TIMEOUT
    return max(_MIN_IDLE_TIMEOUT, min(_MAX_IDLE_TIMEOUT, val))


# Klucze ustawień możliwe do edycji przez API
_UPDATABLE_KEYS = {"n8n_webhook_url", "chat_webhook_url", "allowed_extensions", "idle_timeout_minutes"}
_URL_KEYS = {"n8n_webhook_url", "chat_webhook_url"}


@router.get("/", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all settings as a dictionary."""
    global _cache_loaded
    if not _cache_loaded:
        _load_cache_from_db(db)
    return SettingsResponse(
        n8n_webhook_url=_settings_cache.get("n8n_webhook_url", app_settings.N8N_WEBHOOK_URL) or "",
        chat_webhook_url=_settings_cache.get("chat_webhook_url", "") or "",
        allowed_extensions=_settings_cache.get("allowed_extensions", _DEFAULT_ALLOWED_EXTENSIONS) or "",
        idle_timeout_minutes=get_idle_timeout(),
    )


@router.get("/session")
def get_session_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lekki endpoint dla wszystkich zalogowanych: parametry sesji i wgrywania.

    MUSI być przed '/{key}' (PUT) — tu tylko GET, więc kolizji nie ma, ale trzymamy
    blisko GET '/'. Zwraca wyłącznie wartości niewrażliwe: auto-wylogowanie oraz
    listę dozwolonych rozszerzeń, której okno wysyłki potrzebuje, żeby filtr plików
    i opis zgadzały się z ustawieniem administratora.
    """
    global _cache_loaded
    if not _cache_loaded:
        _load_cache_from_db(db)
    return {
        "idle_timeout_minutes": get_idle_timeout(),
        "allowed_extensions": sorted(get_allowed_extensions()),
    }


@router.put("/{key}")
def update_setting(
    key: str,
    update_data: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a setting value. Tylko administrator."""
    global _settings_cache, _cache_loaded

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zmieniać ustawienia.")

    if key not in _UPDATABLE_KEYS:
        raise HTTPException(status_code=400, detail=f"Setting '{key}' is not updatable")

    new_value = getattr(update_data, key, None)
    if new_value is None or new_value == "":
        raise HTTPException(status_code=400, detail=f"Missing value for setting '{key}'")

    # Walidacja zależna od klucza
    if key == "idle_timeout_minutes":
        try:
            minutes = int(new_value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Czas bezczynności musi być liczbą minut.")
        if minutes < _MIN_IDLE_TIMEOUT or minutes > _MAX_IDLE_TIMEOUT:
            raise HTTPException(status_code=400, detail=f"Czas bezczynności: od {_MIN_IDLE_TIMEOUT} do {_MAX_IDLE_TIMEOUT} minut.")
        new_value = str(minutes)
    elif key in _URL_KEYS:
        if not new_value.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
    elif key == "allowed_extensions":
        exts = _parse_extensions(new_value)
        if not exts:
            raise HTTPException(status_code=400, detail="Podaj co najmniej jedno rozszerzenie (np. pdf,docx,xlsx).")
        if not all(e.isalnum() for e in exts):
            raise HTTPException(status_code=400, detail="Rozszerzenia mogą zawierać tylko litery i cyfry, rozdzielone przecinkami.")
        new_value = ",".join(exts)  # normalizacja (lowercase, bez kropek/spacji)

    # Update cache
    _settings_cache[key] = new_value
    _cache_loaded = True

    # Save to DB
    _save_cache_to_db(db)

    return {"message": "Setting updated", "key": key, "value": new_value}
