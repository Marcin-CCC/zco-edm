"""
Proste testy health check i konfiguracyjne dla FastAPI backend.
Uruchom: pytest backend/tests/ -v
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


# Importujemy aplikację directly — wymaga to mozliwosc importu bez bazy danych
@pytest.fixture
def app():
    """Tworzy aplikacje FastAPI do testow."""
    from app.main import app
    return app


@pytest.fixture
def client(app):
    """Tworzy client do testow."""
    return TestClient(app)


def registered_paths(app) -> list[str]:
    """Zwraca sciezki zarejestrowane w aplikacji (ze schematu OpenAPI).

    Od FastAPI 0.139 include_router nie wplaszcza tras do app.routes,
    tylko dodaje obiekt _IncludedRouter bez atrybutu .path.
    """
    return list(app.openapi()["paths"].keys())


class TestHealthCheck:
    """Testy endpointu health check."""

    def test_root(self, client):
        """Test endpointa root."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "EDM ZCO API dziala poprawnie."
        assert data["version"] == "1.0.0"
        assert data["docs"] == "/docs"

    def test_health_check(self, client):
        """Test endpointu /api/health."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"


class TestConfig:
    """Testy konfiguracji."""

    def test_settings_loaded(self):
        """Test ze ustawienia sa poprawnie zaladowane."""
        from app.config import settings

        # Sprawdzamy ze ustawienia sa obiektem z atrybutami
        assert hasattr(settings, 'DATABASE_URL')
        assert hasattr(settings, 'SECRET_KEY')
        assert hasattr(settings, 'QDRANT_URL')
        assert hasattr(settings, 'ALLOWED_ORIGINS')

    def test_settings_not_empty(self):
        """Test ze kluczowe ustawienia nie sa puste."""
        from app.config import settings

        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0


class TestAuthRouter:
    """Testy routera auth (podstawowe)."""

    def test_login_endpoint_exists(self, app):
        """Test ze endpoint login istnieje."""
        assert '/api/auth/login' in registered_paths(app), \
            "Endpoint /api/auth/login nie zostal znaleziony"

    def test_register_endpoint_exists(self, app):
        """Test ze endpoint register istnieje."""
        assert '/api/auth/register' in registered_paths(app), \
            "Endpoint /api/auth/register nie zostal znaleziony"