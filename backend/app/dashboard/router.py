"""Dashboard statistics endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.schemas import DashboardStats
from app.auth.auth import get_current_user
from app.models import User, File, Folder, DocumentStatus

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Zwraca statystyki dashboardu: użytkownicy, dokumenty, foldery."""
    
    # Licznik użytkowników
    users_count = db.query(func.count(User.id)).scalar()
    
    # Licznik dokumentów/plików
    files_count = db.query(func.count(File.id)).scalar()
    
    # Licznik folderów
    folders_count = db.query(func.count(Folder.id)).scalar()
    
    return DashboardStats(
        users=users_count,
        documents=files_count,
        folders=folders_count,
        processed=0,  # TODO: podłączymy gdy procesowanie będzie działać
    )