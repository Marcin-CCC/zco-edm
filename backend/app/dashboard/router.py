"""Dashboard statistics endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date

from app.database import get_db
from app.schemas import DashboardStats
from app.auth.auth import get_current_user
from app.models import User, File, Folder, DocumentStatus, Conversation, Message
from app.rbac import readable_folder_ids
from app.dashboard.system_status import zbierz

router = APIRouter(tags=["Dashboard"])


# Najmniejsza podstawa, przy której procent cokolwiek znaczy. Zmierzone na bazie
# ZCO 2026-08-16: system ma sześć tygodni, więc porównanie z „stanem sprzed 30 dni"
# dawało +800% dla kont i +5200% dla folderów — liczby prawdziwe i bezużyteczne.
# Procent liczony od jedynki nie jest informacją, tylko ozdobą.
MIN_PODSTAWA_TRENDU = 10


def _zmiana_procentowa(teraz: int, wczesniej: int) -> float | None:
    """Zmiana w procentach wobec stanu sprzed okresu.

    ``None`` gdy: brak odniesienia (wcześniej zero), zbyt mała podstawa albo brak
    zmiany. Interfejs pokazuje wtedy sam licznik, bez drugiej linijki — kafelek
    z „→ 0,0%" albo „↑ 5200%" niósłby mniej niż jego brak.
    """
    if wczesniej < MIN_PODSTAWA_TRENDU or teraz == wczesniej:
        return None
    return round((teraz - wczesniej) / wczesniej * 100, 1)


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
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

    dokumenty = q_files.scalar()
    przetworzone = q_ready.scalar()

    # Stan sprzed okresu liczymy z dat utworzenia — bez osobnej tabeli migawek.
    # Wystarcza, bo wiersze nie znikają: skasowany dokument i tak nie powinien
    # podbijać „wzrostu" wstecz.
    granica = datetime.utcnow() - timedelta(days=days)
    q_files_przed = db.query(func.count(File.id)).filter(File.created_at < granica)
    q_ready_przed = q_files_przed.filter(File.status == DocumentStatus.READY)
    if readable is not None:
        q_files_przed = q_files_przed.filter(File.folder_id.in_(readable))
        q_ready_przed = q_ready_przed.filter(File.folder_id.in_(readable))
        folders_przed = db.query(func.count(Folder.id)).filter(
            Folder.id.in_(readable), Folder.created_at < granica
        ).scalar()
        users_przed = None
    else:
        folders_przed = db.query(func.count(Folder.id)).filter(Folder.created_at < granica).scalar()
        users_przed = db.query(func.count(User.id)).filter(User.created_at < granica).scalar()

    dokumenty_przed = q_files_przed.scalar()
    przetworzone_przed = q_ready_przed.scalar()
    # „Przetworzone" to udział procentowy, więc porównujemy udziały, nie liczby.
    udzial = (przetworzone / dokumenty * 100) if dokumenty else 0.0
    udzial_przed = (przetworzone_przed / dokumenty_przed * 100) if dokumenty_przed else 0.0

    return DashboardStats(
        users=users_count,
        documents=dokumenty,
        folders=folders_count,
        processed=przetworzone,
        processed_percent=round(udzial, 1),
        trend_users=_zmiana_procentowa(users_count, users_przed) if users_count is not None else None,
        trend_folders=_zmiana_procentowa(folders_count, folders_przed),
        trend_documents=_zmiana_procentowa(dokumenty, dokumenty_przed),
        trend_processed=(
            round(udzial - udzial_przed, 1) if udzial_przed and abs(udzial - udzial_przed) >= 0.05 else None
        ),
        trend_days=days,
    )


@router.get("/dashboard/recent-files")
def get_recent_files(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Ostatnio dodane dokumenty — rzut oka na Dashboardzie, nie zamiennik listy plików.

    Zakres jak wszędzie: administrator widzi wszystko, pozostali tylko pliki
    z folderów dostępnych ich roli.
    """
    readable = readable_folder_ids(current_user, db)
    q = db.query(File)
    if readable is not None:
        q = q.filter(File.folder_id.in_(readable))
    pliki = q.order_by(File.created_at.desc(), File.id.desc()).limit(limit).all()

    return [
        {
            "id": f.id,
            "filename": f.filename,
            "folder": f.folder.path if f.folder else None,
            "size": f.size,
            "status": f.status.value if hasattr(f.status, "value") else str(f.status),
            "doc_type": f.doc_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in pliki
    ]


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
    is_admin = current_user.is_admin
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

@router.get("/dashboard/by-user")
def get_activity_by_user(
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktywność w rozbiciu na użytkowników — wyłącznie dla administratora.

    Zwraca dla każdego konta liczbę plików wysłanych do przetworzenia i liczbę pytań
    zadanych bazie wiedzy w ostatnich N dniach. Konta bez aktywności też są na liście:
    brak słupka jest tu informacją, a nie luką.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator widzi podział na użytkowników.")

    today = datetime.utcnow().date()
    start_day = today - timedelta(days=days - 1)
    od = datetime.combine(start_day, datetime.min.time())

    # Sparsowane pliki: moment przetwarzania jak na wykresie dziennym
    # (metadata.processing_started_at, a przy jego braku data dodania).
    parsed: dict[int, int] = {}
    for f in db.query(File).filter(File.status == DocumentStatus.READY).all():
        meta = f.metadata_ if isinstance(f.metadata_, dict) else {}
        moment = None
        started = meta.get("processing_started_at")
        if started:
            try:
                moment = datetime.fromisoformat(started).date()
            except (ValueError, TypeError):
                moment = None
        if moment is None and f.created_at:
            moment = f.created_at.date()
        if moment and moment >= start_day and f.uploaded_by:
            parsed[f.uploaded_by] = parsed.get(f.uploaded_by, 0) + 1

    queries: dict[int, int] = {}
    wiersze = (
        db.query(Conversation.user_id, func.count(Message.id))
        .join(Message, Message.conversation_id == Conversation.id)
        .filter(Message.role == "user")
        .filter(Message.created_at >= od)
        .group_by(Conversation.user_id)
        .all()
    )
    for user_id, ile in wiersze:
        queries[user_id] = int(ile)

    konta = db.query(User).all()
    # Kilka kont potrafi mieć to samo imię i nazwisko. Na wykresie byłyby wtedy
    # nierozróżnialne, więc powtórzone nazwy uzupełniamy o login.
    ile_nazw: dict[str, int] = {}
    for u in konta:
        nazwa = (u.full_name or u.username or u.email or f"#{u.id}").strip()
        ile_nazw[nazwa] = ile_nazw.get(nazwa, 0) + 1

    osoby = []
    for u in konta:
        nazwa = (u.full_name or u.username or u.email or f"#{u.id}").strip()
        if ile_nazw.get(nazwa, 0) > 1 and u.username:
            nazwa = f"{nazwa} ({u.username})"
        osoby.append({
            "user_id": u.id,
            "name": nazwa,
            "parsed": parsed.get(u.id, 0),
            "queries": queries.get(u.id, 0),
        })
    # Wspólna kolejność dla obu wykresów — łatwiej zestawić je wzrokiem niż przy
    # dwóch różnych sortowaniach.
    osoby.sort(key=lambda o: (-(o["parsed"] + o["queries"]), o["name"].lower()))
    return {"days": days, "users": osoby}


@router.get("/dashboard/system-status")
def get_system_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stan serwera pod panele „Status systemu" i „Miejsce w systemie".

    Tylko dla administratora — tak jak licznik kont w statystykach. Zwykły
    użytkownik nie ma co zrobić z informacją, że dysk Sparka jest zajęty w 19%,
    a wolne miejsce na serwerze i obciążenie to dane o infrastrukturze klienta.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Stan serwera widzi tylko administrator.")
    return zbierz(db)
