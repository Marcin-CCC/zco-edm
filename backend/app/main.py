import logging
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ============ LOGOWANIE ============
# Uvicorn konfiguruje wyłącznie własne loggery ("uvicorn.*"). Bez poniższego
# root logger zostaje z poziomem WARNING i bez handlerów, więc wszystkie
# logger.info() aplikacji ([DISPATCH], [UPLOAD], [CHAT], [SPARK-TRANSFER])
# są po cichu wyrzucane. Musi wykonać się PRZED importami modułów aplikacji.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    stream=sys.stdout,
)

# Dodaj parent directory do path dla importów
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base
from app.config import settings

# Import routerów
from app.auth.auth import router as auth_router
from app.files import router as files_router
from app.folders import router as folders_router
from app.storage.router import router as storage_router
from app.webhooks.router import router as webhooks_router
from app.dashboard.router import router as dashboard_router
from app.version_router import router as version_router
from app.processing_queue.router import router as processing_queue_router
from app.settings.router import router as settings_router
from app.chat.router import router as chat_router
from app.doc_schemas import router as doc_schemas_router
from app.doc_search import router as doc_search_router
from app.roles.router import router as roles_router
from app.schema_upgrade import run_startup_upgrades

# Tworzenie tabel w bazie danych
Base.metadata.create_all(bind=engine)

# To, czego `create_all` nie potrafi: zmiana typu istniejących kolumn i zasianie
# słownika ról. Wykonuje się przy każdym starcie i jest idempotentne.
run_startup_upgrades(engine)

# ============ APLIKACJA FASTAPI ============
# Nazwa instancji pochodzi z konfiguracji — jeden obraz obsługuje demo uniwersalne
# (HIRS) i wdrożenia klienckie, które różnią się wyłącznie zmiennymi środowiskowymi.
NAZWA_APLIKACJI = os.getenv("APP_NAME", "HIRS")

app = FastAPI(
    title=f"{NAZWA_APLIKACJI} - API",
    version="1.0.0"
)

# ============ CORS ============
allowed_origins = settings.ALLOWED_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ KOLEJKA PRZETWARZANIA (dyspozytor) ============
@app.on_event("startup")
async def resume_processing_queue():
    """Po starcie backendu wznów kolejkę (np. po restarcie w trakcie pracy)
    i uruchom pętlę watchdoga pilnującą zawieszonych plików."""
    import asyncio
    import logging
    from app.database import SessionLocal
    from app.dispatcher import try_dispatch_next

    logger = logging.getLogger(__name__)

    async def _dispatch_once(context: str):
        db = SessionLocal()
        try:
            result = await try_dispatch_next(db)
            logger.info(f"[QUEUE] {context}: {result}")
        except Exception as e:
            logger.error(f"[QUEUE] {context} błąd: {e}")
        finally:
            db.close()

    # Indeks pełnotekstowy w kolekcji tej instancji — bez niego dopasowanie po słowie
    # zwraca zero dla wszystkiego i psuje zawężanie leksykalne oraz wykrywanie skrótów
    # spoza dokumentów. Idempotentne, więc kosztuje jedno zapytanie przy starcie.
    try:
        from app.qdrant_client import ensure_text_index
        ensure_text_index()
    except Exception as e:
        logger.warning(f"[QUEUE] Kontrola indeksu Qdranta nieudana: {e}")

    await _dispatch_once("startup")

    async def _watchdog_loop():
        while True:
            await asyncio.sleep(300)  # co 5 minut
            await _dispatch_once("watchdog")

    asyncio.create_task(_watchdog_loop())


# ============ ROUTERY ============
app.include_router(auth_router, prefix="/api")
app.include_router(files_router)
app.include_router(folders_router, prefix="/api")
app.include_router(storage_router)
app.include_router(webhooks_router)
app.include_router(dashboard_router, prefix="/api")
app.include_router(version_router)
app.include_router(processing_queue_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(doc_schemas_router)
app.include_router(doc_search_router)
app.include_router(roles_router)


# ============ HEALTH CHECK ============
@app.get("/")
def read_root():
    return {
        "message": f"{NAZWA_APLIKACJI} API dziala poprawnie.",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "database": "connected"
    }


@app.get("/api/health/info")
def health_info():
    """Nowy endpoint z dodatkowymi informacjami o wdrozeniu."""
    from datetime import datetime, timezone
    return {
        "status": "ok",
        "database": "connected",
        "deployment_type": "github-actions-cicd",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ci_cd": "GitHub Actions",
        "message": "Wdrozenie przez GitHub Actions CI/CD - TEST"
    }
