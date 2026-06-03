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
        # Szukamy endpointu POST /api/auth/login
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        login_routes = [r for r in routes if '/api/auth/login' in r.path]
        
        assert len(login_routes) > 0, "Endpoint /api/auth/login nie zostal znaleziony"

    def test_register_endpoint_exists(self, app):
        """Test ze endpoint register istnieje."""
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        register_routes = [r for r in routes if '/api/auth/register' in r.path]
        
        assert len(register_routes) > 0, "Endpoint /api/auth/register nie zostal znaleziony"