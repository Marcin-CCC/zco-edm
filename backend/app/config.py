import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Ustawienia aplikacji pobierane ze zmiennych środowiskowych."""

    # Baza danych
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:tajne_haslo@127.0.0.1:15432/edmdatabase"
    )

    # Bezpieczeństwo
    SECRET_KEY: str = os.getenv("SECRET_KEY", "zco-edm-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    # CORS
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001"
    )

    # Storage
    STORAGE_PATH: str = os.getenv(
        "STORAGE_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared_docs")
    )

    # External services
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://192.168.1.34:6333")
    N8N_WEBHOOK_URL: str = os.getenv("N8N_WEBHOOK_URL", "http://192.168.1.34:5678/webhook/document-uploaded")
    DOCLING_API_URL: str = os.getenv("DOCLING_API_URL", "http://127.0.0.1:8002")
    OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://192.168.1.34:11434")


settings = Settings()