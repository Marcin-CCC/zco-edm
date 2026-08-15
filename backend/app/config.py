import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text

load_dotenv()


class Settings:
    """Ustawienia aplikacji pobierane ze zmiennych środowiskowych."""

    # Środowisko uruchomienia: "dev" (domyślnie) albo "production". NIE służy do
    # włączania funkcji — jedynym jego zadaniem jest bezpiecznik
    # `assert_environment_is_consistent` na dole tego pliku. Produkcja ustawia
    # `APP_ENV=production` w pliku `.env` pisanym przez CI.
    APP_ENV: str = os.getenv("APP_ENV", "dev")

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

    # Nazwa TEJ instancji („ZCO DM", „HiRS"). Backend potrzebuje jej, bo jeden
    # workflow n8n obsługuje oba wdrożenia i raporty e-mail z obu wyglądały
    # identycznie — nie dało się poznać, z którego systemu przyszedł raport.
    APP_NAME: str = os.getenv("APP_NAME", "HiRS")

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

    # Czy pod odpowiedzią czatu prosić użytkownika o ocenę. Domyślnie WŁĄCZONE:
    # pierwsza grupa użytkowników jest szkolona, żeby oceniać zawsze. We wdrożeniu
    # docelowym da się to wyłączyć jedną zmienną, jeśli okaże się, że korzysta
    # z tego znikomy procent osób.
    OCENY_ODPOWIEDZI: bool = os.getenv("OCENY_ODPOWIEDZI", "1").lower() not in (
        "0", "false", "nie", "no"
    )


settings = Settings()


# ==================== Bezpiecznik środowiska ====================
# Hosty uznawane za „ta sama maszyna". Świadomie nie ma tu nazw usług z compose
# (`postgres`, `db`) — wpisanie ich uczyniłoby kontrolę bezużyteczną akurat na
# serwerze, gdzie baza nazywa się tak samo jak w każdym innym pliku compose.
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


def database_host(database_url: str) -> str | None:
    """Host z adresu bazy. ``None``, gdy adres go nie ma (np. sqlite w testach)."""
    try:
        return urlsplit(database_url).hostname
    except ValueError:
        return None


def assert_environment_is_consistent(app_env: str, database_url: str) -> None:
    """Nie pozwala środowisku deweloperskiemu dotknąć zdalnej bazy.

    Powód jest z pierwszej ręki (2026-08-15): dev-stack z zamontowanym kodem
    z dysku i `DATABASE_URL` wskazującym Sparka wstał razem z Dockerem i wykonał
    migrację schematu na produkcyjnej bazie klienta. Nikt tego nie zlecił —
    wystarczyło, że kontener istniał.

    Sama konfiguracja tego nie zatrzyma, bo to właśnie konfiguracja bywa
    pomyłką. Dlatego aplikacja ma ODMÓWIĆ STARTU. Dostęp do zdalnej bazy wymaga
    świadomego ustawienia `APP_ENV=production` — a to już jest decyzja, nie
    przypadek.
    """
    if app_env == "production":
        return
    host = database_host(database_url)
    if host is None or host in LOCAL_DB_HOSTS:
        return
    raise RuntimeError(
        f"Odmowa startu: APP_ENV={app_env!r} (środowisko deweloperskie), "
        f"a DATABASE_URL wskazuje na zdalny host {host!r}. "
        "Kod deweloperski nie może pisać do bazy innej niż lokalna. "
        "Ustaw DATABASE_URL na lokalną bazę (patrz spark-deploy/snapshot-dev.sh) "
        "albo — jeśli naprawdę uruchamiasz produkcję — ustaw APP_ENV=production."
    )


# Wartości domyślne z repozytorium. Każda, kto zna repozytorium, zna je także —
# a kluczem podpisywany jest token sesji, więc znajomość tej wartości pozwala
# wystawić sobie token administratora.
PLACEHOLDER_SECRET_KEYS = frozenset({
    "zco-edm-secret-key-change-in-production",
    "hirs-demo-secret-change-me",
    "your-secret-key",
    "",
})
MIN_SECRET_KEY_LENGTH = 32


def assert_secret_key_is_safe(app_env: str, secret_key: str) -> None:
    """Produkcja nie może podpisywać tokenów wartością domyślną z repozytorium.

    Do 2026-08-15 obie instancje robiły dokładnie to: CI nie zapisywał
    `SECRET_KEY` do pliku `.env`, więc compose podstawiał domyślkę leżącą
    w repozytorium — łańcuch, który wprost mówi „change-in-production".

    Ta kontrola jest tu z tego samego powodu co bezpiecznik bazy: zmienna
    środowiskowa, o której wszyscy pamiętają, nie istnieje. Musi jej pilnować
    kod, i to odmową startu — cicha praca z domyślnym kluczem wygląda dokładnie
    tak samo jak praca z prawidłowym.
    """
    if app_env != "production":
        return
    if secret_key in PLACEHOLDER_SECRET_KEYS or len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            "Odmowa startu: SECRET_KEY nie został ustawiony dla produkcji "
            f"(wymagane min. {MIN_SECRET_KEY_LENGTH} znaków, wartości domyślne z repozytorium "
            "są odrzucane). "
            "Tym kluczem podpisywane są tokeny sesji — domyślka z repozytorium pozwala "
            "każdemu, kto ją zna, wystawić sobie token administratora. "
            "Ustaw sekret w repozytorium (gh secret set SECRET_KEY); CI wpisuje go do .env."
        )

