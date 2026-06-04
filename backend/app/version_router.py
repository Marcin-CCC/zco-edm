"""Version API router."""
from fastapi import APIRouter
from app.version import get_version_info

router = APIRouter()


@router.get("/api/version")
def get_version():
    """Zwraca informacje o wersji aplikacji."""
    return get_version_info()