"""
Testy endpointow plikow: upload, list, queue, status-summary.
Uruchom: pytest backend/tests/test_files_queue.py -v
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os


@pytest.fixture
def app():
    """Tworzy aplikacje FastAPI do testow."""
    from app.main import app
    return app


@pytest.fixture
def client(app):
    """Tworzy client do testow."""
    return TestClient(app)


class TestFilesQueueEndpoint:
    """Testy endpointu /api/files/queue."""

    def test_queue_endpoint_exists(self, app):
        """Test ze endpoint /api/files/queue istnieje."""
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        queue_routes = [r for r in routes if '/api/files/queue' in r.path]
        assert len(queue_routes) > 0, "Endpoint /api/files/queue nie zostal znaleziony"

    def test_queue_endpoint_returns_401_without_auth(self, client):
        """Test ze endpoint zwraca 401 bez autoryzacji."""
        response = client.get("/api/files/queue")
        assert response.status_code == 401

    def test_status_summary_endpoint_exists(self, app):
        """Test ze endpoint /api/files/status-summary istnieje."""
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        summary_routes = [r for r in routes if '/api/files/status-summary' in r.path]
        assert len(summary_routes) > 0, "Endpoint /api/files/status-summary nie zostal znaleziony"

    def test_status_summary_returns_401_without_auth(self, client):
        """Test ze endpoint zwraca 401 bez autoryzacji."""
        response = client.get("/api/files/status-summary")
        assert response.status_code == 401


class TestFilesUploadEndpoint:
    """Testy endpointu /api/files/upload."""

    def test_upload_endpoint_exists(self, app):
        """Test ze endpoint /api/files/upload istnieje."""
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        upload_routes = [r for r in routes if r.path == '/api/files/upload']
        assert len(upload_routes) > 0, "Endpoint /api/files/upload nie zostal znaleziony"

    def test_upload_returns_401_without_auth(self, client):
        """Test ze endpoint zwraca 401 bez autoryzacji."""
        response = client.post("/api/files/upload")
        assert response.status_code == 401


class TestFilesListEndpoint:
    """Testy endpointu /api/files/."""

    def test_list_endpoint_exists(self, app):
        """Test ze endpoint /api/files/ istnieje."""
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        list_routes = [r for r in routes if r.path == '/api/files/']
        assert len(list_routes) > 0, "Endpoint /api/files/ nie zostal znaleziony"

    def test_list_returns_401_without_auth(self, client):
        """Test ze endpoint zwraca 401 bez autoryzacji."""
        response = client.get("/api/files/")
        assert response.status_code == 401


class TestDocumentStatusEnum:
    """Testy enum DocumentStatus."""

    def test_document_status_has_all_values(self):
        """Test ze enum DocumentStatus ma wszystkie wartosci."""
        from app.models import DocumentStatus
        
        assert hasattr(DocumentStatus, 'PENDING')
        assert hasattr(DocumentStatus, 'PARSING')
        assert hasattr(DocumentStatus, 'PENDING_CHUNKING')
        assert hasattr(DocumentStatus, 'PENDING_VECTORIZE')
        assert hasattr(DocumentStatus, 'READY')
        assert hasattr(DocumentStatus, 'ERROR')

    def test_document_status_values(self):
        """Test wartosci enum DocumentStatus."""
        from app.models import DocumentStatus
        
        assert DocumentStatus.PENDING.value == "W kolejce (n8n)"
        assert DocumentStatus.PARSING.value == "Parsowanie (Docling)"
        assert DocumentStatus.PENDING_CHUNKING.value == "Chunkowanie"
        assert DocumentStatus.PENDING_VECTORIZE.value == "Wektoryzacja (Qdrant)"
        assert DocumentStatus.READY.value == "Przetworzono"
        assert DocumentStatus.ERROR.value == "Błąd przetwarzania"

    def test_status_value_conversion(self):
        """Test konwersji wartosci statusu na string."""
        from app.models import DocumentStatus
        
        for status in DocumentStatus:
            value = status.value if hasattr(status, 'value') else str(status)
            assert isinstance(value, str)
            assert len(value) > 0


class TestFileModel:
    """Testy modelu File."""

    def test_file_model_has_status_column(self):
        """Test ze model File ma kolumnę status."""
        from app.models import File
        
        assert hasattr(File, 'status')
        assert hasattr(File, 'filename')
        assert hasattr(File, 'file_path')
        assert hasattr(File, 'mime_type')
        assert hasattr(File, 'size')
        assert hasattr(File, 'folder_id')
        assert hasattr(File, 'uploaded_by')
        assert hasattr(File, 'created_at')
        assert hasattr(File, 'updated_at')

    def test_file_table_name(self):
        """Test nazwy tabeli File."""
        from app.models import File
        
        assert File.__tablename__ == 'files'


class TestRoutesRegistration:
    """Testy rejestracji routerow."""

    def test_all_routes_registered(self, app):
        """Test ze wszystkie route'y sa zarejestrowane."""
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path]
        paths = [r.path for r in routes]
        
        expected_paths = [
            '/api/files/',
            '/api/files/upload',
            '/api/files/queue',
            '/api/files/status-summary',
            '/api/files/{file_id}',
            '/api/files/{file_id}/download',
            '/api/files/{file_id}',
            '/api/files/categories',
            '/api/files/folder/{folder_id}/files',
        ]
        
        for path in expected_paths:
            # Sprawdzamy czy jakis endpoint zawiera sciezke
            matching = [p for p in paths if path.replace('{', '/').replace('}', '') in p]
            assert len(matching) > 0, f"Endpoint {path} nie zostal znaleziony"
