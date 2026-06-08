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
        n8n_webhook_url=_settings_cache.get("n8n_webhook_url", app_settings.N8N_WEBHOOK_URL)
    )


@router.put("/{key}")
def update_setting(
    key: str,
    update_data: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a setting value. Only n8n_webhook_url is supported."""
    global _settings_cache, _cache_loaded

    if key != "n8n_webhook_url":
        raise HTTPException(status_code=400, detail=f"Setting '{key}' is not updatable")

    # Validate URL format
    new_value = update_data.n8n_webhook_url
    if not new_value.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")

    # Update cache
    _settings_cache[key] = new_value
    _cache_loaded = True

    # Save to DB
    _save_cache_to_db(db)

    return {"message": "Setting updated", "key": key, "value": new_value}
