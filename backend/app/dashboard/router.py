"""Dashboard statistics endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date

from app.database import get_db
from app.schemas import DashboardStats
from app.auth.auth import get_current_user
from app.models import User, File, Folder, DocumentStatus, Conversation, Message, UserRole
from app.rbac import readable_folder_ids

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Statystyki dashboardu w zakresie widoczności użytkownika.

    Administrator widzi całość wraz z liczbą kont. Zwykły użytkownik — tylko
    foldery, do których jego rola ma dostęp, i pliki w nich leżące; licznika
    użytkowników nie dostaje wcale (None → kafelek znika w interfejsie).
    Te same reguły co na liście plików, żeby liczby na Dashboardzie zgadzały się
    z tym, co użytkownik realnie widzi w Eksploratorze.
    """
    readable = readable_folder_ids(current_user, db)  # None = admin, bez ograniczeń

    q_files = db.query(func.count(File.id))
    q_ready = db.query(func.count(File.id)).filter(File.status == DocumentStatus.READY)
    if readable is None:
        folders_count = db.query(func.count(Folder.id)).scalar()
        users_count = db.query(func.count(User.id)).scalar()
    else:
        # pliki bez folderu (root) są poza zasięgiem nie-admina — jak na liście plików
        q_files = q_files.filter(File.folder_id.in_(readable))
        q_ready = q_ready.filter(File.folder_id.in_(readable))
        folders_count = len(readable)
        users_count = None

    return DashboardStats(
        users=users_count,
        documents=q_files.scalar(),
        folders=folders_count,
        processed=q_ready.scalar(),
    )


@router.get("/dashboard/activity")
def get_activity(
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dzienne liczniki z ostatnich N dni: sparsowane pliki i zapytania w czacie.

    Zakres danych zależy od roli: administrator widzi całość, pozostali — pliki
    z folderów, do których mają dostęp (nie tylko wgrane przez siebie), oraz
    własne zapytania w czacie, bo te są sprawą osobistą.

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
    readable = readable_folder_ids(current_user, db)
    if readable is not None:
        q_files = q_files.filter(File.folder_id.in_(readable))
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