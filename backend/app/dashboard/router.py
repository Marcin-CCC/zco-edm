"""Dashboard statistics endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date

from app.database import get_db
from app.schemas import DashboardStats
from app.auth.auth import get_current_user
from app.models import User, File, Folder, DocumentStatus, Conversation, Message, UserRole

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

    # Licznik przetworzonych plików (status READY = "Przetworzono")
    processed_count = (
        db.query(func.count(File.id))
        .filter(File.status == DocumentStatus.READY)
        .scalar()
    )

    return DashboardStats(
        users=users_count,
        documents=files_count,
        folders=folders_count,
        processed=processed_count,
    )


@router.get("/dashboard/activity")
def get_activity(
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dzienne liczniki z ostatnich N dni: sparsowane pliki i zapytania w czacie.

    Zakres danych zależy od roli: administrator widzi wszystkich użytkowników,
    pozostali wyłącznie własne pliki i własne zapytania.

    Dni bez zdarzeń zwracamy jako zera — wykres ma mieć ciągłą oś czasu, a nie
    tylko dni, w których coś się wydarzyło.
    """
    is_admin = current_user.role == UserRole.ADMIN
    today = datetime.utcnow().date()
    start_day = today - timedelta(days=days - 1)
    dni = [start_day + timedelta(days=i) for i in range(days)]

    # --- Sparsowane pliki ---
    # Za moment sparsowania bierzemy start przetwarzania (metadata.processing_started_at),
    # a gdy go brak (pliki sprzed wprowadzenia pomiaru) — datę dodania.
    parsed = {d: 0 for d in dni}
    q_files = db.query(File).filter(File.status == DocumentStatus.READY)
    if not is_admin:
        q_files = q_files.filter(File.uploaded_by == current_user.id)
    for f in q_files.all():
        moment = None
        meta = f.metadata_ if isinstance(f.metadata_, dict) else {}
        started = meta.get("processing_started_at")
        if started:
            try:
                moment = datetime.fromisoformat(started).date()
            except (ValueError, TypeError):
                moment = None
        if moment is None and f.created_at:
            moment = f.created_at.date()
        if moment in parsed:
            parsed[moment] += 1

    # --- Zapytania w czacie (wiadomości użytkownika) ---
    queries = {d: 0 for d in dni}
    q_msg = (
        db.query(func.date(Message.created_at), func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Message.role == "user")
        .filter(Message.created_at >= datetime.combine(start_day, datetime.min.time()))
    )
    if not is_admin:
        q_msg = q_msg.filter(Conversation.user_id == current_user.id)
    for dzien, ile in q_msg.group_by(func.date(Message.created_at)).all():
        d = dzien if isinstance(dzien, date) else datetime.fromisoformat(str(dzien)).date()
        if d in queries:
            queries[d] = ile

    return {
        "days": [d.isoformat() for d in dni],
        "parsed": [parsed[d] for d in dni],
        "queries": [queries[d] for d in dni],
        "scope": "all" if is_admin else "own",
    }