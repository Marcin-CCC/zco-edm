import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# Tworzenie tabel w bazie danych
Base.metadata.create_all(bind=engine)

# ============ APLIKACJA FASTAPI ============
app = FastAPI(
    title="EDM ZCO - API",
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


# ============ HEALTH CHECK ============
@app.get("/")
def read_root():
    return {
        "message": "EDM ZCO API dziala poprawnie.",
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
