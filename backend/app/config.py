import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text

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
    # Absolutny backstop sesji (token JWT). Główny mechanizm wylogowania to
    # bezczynność (po stronie frontendu, konfigurowalna w Ustawieniach). Ten
    # limit chroni na wypadek np. kradzieży tokenu. 720 min = 12h (aby nie ucinać
    # sesji osobom pracującym 9–10h ciągiem).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720")
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
    # Kolekcja Qdrant, do której n8n zapisuje wektory (do usuwania po file_id).
    # Nazwa "chi_camp_2026" to pozostałość po szablonie n8n — konfigurowalna,
    # gdyby została przemianowana przy czyszczeniu bazy demo.
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "chi_camp_2026")
    N8N_WEBHOOK_URL: str = os.getenv("N8N_WEBHOOK_URL")  # Pobierany z ustawień aplikacji (baza danych)
    DOCLING_API_URL: str = os.getenv("DOCLING_API_URL", "http://docling:8002")
    OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://192.168.1.34:11434")

    # vLLM (OpenAI-compatible) — klasyfikacja i ekstrakcja pól (#7B-2).
    # Ten sam model, którego używa czat/parsowanie; arbitraż dostępu w app/activity.py.
    VLLM_URL: str = os.getenv("VLLM_URL", "http://192.168.1.34:8002")
    VLLM_MODEL: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-VL-30B-A3B-Instruct")

    # Czy wskazywanie dokumentów ma korzystać ze streszczeń SEKCYJNYCH obok
    # streszczeń całych dokumentów (zob. app/sekcje.py). Domyślnie WYŁĄCZONE:
    # sekcje dokładają ~290 celów do warstwy, która nie rozdziela trafień od
    # nietrafień wartością score, więc włączamy je dopiero po pomiarze
    # (app/retrieval_bench.py). Przełącznik zostaje, żeby dało się wrócić.
    SEKCJE_W_WYSZUKIWANIU: bool = os.getenv("SEKCJE_W_WYSZUKIWANIU", "").lower() in (
        "1", "true", "tak", "yes"
    )


settings = Settings()