"""Version API router."""
from fastapi import APIRouter
from app.version import get_version_info, get_changelog

router = APIRouter()


@router.get("/api/version")
def get_version():
    """Zwraca informacje o wersji aplikacji."""
    return get_version_info()


@router.get("/api/changelog")
def changelog():
    """Zwraca historię zmian (lista wydań, najnowsze pierwsze)."""
    return {"entries": get_changelog()}