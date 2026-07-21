"""
Dyspozytor kolejki przetwarzania — 1 plik naraz.

Zasada działania:
- Upload NIE wywołuje webhooka n8n bezpośrednio. Plik ląduje w DB
  ze statusem PENDING ("W kolejce (n8n)").
- Dyspozytor (try_dispatch_next) sprawdza, czy jakiś plik jest w statusie
  PROCESSING. Jeśli nie — bierze najstarszy PENDING, wywołuje webhook n8n
  i czeka na callback (PATCH /api/webhook/file/{id}/status).
- Callback READY/ERROR ponownie woła try_dispatch_next → następny plik.
- Watchdog: plik w PROCESSING dłużej niż PROCESSING_TIMEOUT_MINUTES jest
  oznaczany jako ERROR (n8n umarł w trakcie), a kolejka rusza dalej.

Dyspozytor "zajmuje slot" (claim): ustawia status PROCESSING sam, zanim
wyśle webhook. Nod PROCESSING w n8n jest wtedy idempotentny (nadpisuje tym
samym statusem). Dzięki temu stan kolejki żyje wyłącznie w kolumnie
files.status i przeżywa restart backendu.

Współbieżność (jedna baza, wiele backendów — dev lokalny + Spark):
- Sekcja "decyzja + zajęcie slotu" jest serializowana blokadą doradczą
  Postgresa (pg_advisory_xact_lock). Dzięki temu dwa backendy dzielące bazę
  nie wyślą dwóch plików naraz — gwarancja "1 plik naraz" trzyma się
  niezależnie od liczby instancji. Blokada trzyma się do commitu (krótko:
  tylko na czas decyzji), a POST do n8n leci już POZA blokadą.
"""

import os
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import File as FileModel, DocumentStatus
from app.n8n_auth import outgoing_headers

logger = logging.getLogger(__name__)

# Po ilu minutach plik wiszący w PROCESSING uznajemy za martwy (watchdog)
PROCESSING_TIMEOUT_MINUTES = int(os.getenv("PROCESSING_TIMEOUT_MINUTES", "30"))

# Stały klucz blokady doradczej dyspozytora — TEN SAM we wszystkich instancjach
# dzielących bazę, więc serializuje wysyłkę między nimi.
_DISPATCH_LOCK_KEY = 776_2001


def _get_webhook_url(db: Session) -> str | None:
    """Webhook URL z ustawień aplikacji (DB) z fallbackiem na env."""
    from app.settings.router import _load_cache_from_db, get_webhook_url
    _load_cache_from_db(db)
    return get_webhook_url()


def _build_payload(file: FileModel) -> dict:
    from app.files.router import build_webhook_payload
    return build_webhook_payload(file.id, file.file_path)


def _reap_stale_processing(db: Session) -> None:
    """Watchdog: oznacz jako ERROR pliki wiszące w PROCESSING zbyt długo.

    Nie commituje — wołane w sekcji krytycznej dyspozytora, commit robi
    wołający (żeby reap i decyzja o zajęciu slotu były jedną transakcją).
    """
    cutoff = datetime.utcnow() - timedelta(minutes=PROCESSING_TIMEOUT_MINUTES)
    stale = (
        db.query(FileModel)
        .filter(FileModel.status == DocumentStatus.PROCESSING)
        .filter(FileModel.updated_at < cutoff)
        .all()
    )
    for f in stale:
        logger.warning(
            f"[DISPATCH] Watchdog: plik {f.id} ({f.filename}) w PROCESSING "
            f"od > {PROCESSING_TIMEOUT_MINUTES} min — oznaczam ERROR"
        )
        f.status = DocumentStatus.ERROR


def _mark_error(db: Session, file_id: int, reason: str | None = None) -> None:
    """Ustaw ERROR dla pliku po ID i zapisz powód w metadanych (do UI)."""
    f = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not f:
        return
    f.status = DocumentStatus.ERROR
    if reason:
        meta = dict(f.metadata_ or {})
        meta["error"] = reason[:1000]
        f.metadata_ = meta
    db.commit()


def _revert_to_pending(db: Session, file_id: int) -> None:
    """Zwolnij zajęty slot: PROCESSING → PENDING (awaria przejściowa n8n).

    Plik wraca do kolejki i zostanie ponowiony przy następnym cyklu dyspozytora
    (upload/callback lub watchdog co 5 min) — bez spalania go na ERROR, gdy n8n
    tylko chwilowo nie odpowiada.
    """
    db.query(FileModel).filter(FileModel.id == file_id).update(
        {FileModel.status: DocumentStatus.PENDING}
    )
    db.commit()


async def try_dispatch_next(db: Session) -> dict:
    """Uruchom przetwarzanie następnego pliku, jeśli nic się nie przetwarza.

    Zwraca słownik diagnostyczny:
      {"dispatched": bool, "file_id": int|None, "reason": str}
    """
    # ===== Sekcja krytyczna: decyzja + zajęcie slotu pod blokadą doradczą =====
    # pg_advisory_xact_lock serializuje ten fragment między WSZYSTKIMI backendami
    # dzielącymi bazę. Trzyma się do commitu (krótko). POST do n8n jest później,
    # już poza blokadą. Na nie-Postgresie (np. testy) blokadę pomijamy.
    try:
        if db.bind and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _DISPATCH_LOCK_KEY})

        _reap_stale_processing(db)

        in_flight = (
            db.query(FileModel)
            .filter(FileModel.status == DocumentStatus.PROCESSING)
            .count()
        )
        if in_flight > 0:
            db.commit()  # zapisz reap, zwolnij blokadę
            return {"dispatched": False, "file_id": None,
                    "reason": f"{in_flight} plik(ów) w trakcie przetwarzania"}

        next_file = (
            db.query(FileModel)
            .filter(FileModel.status == DocumentStatus.PENDING)
            .order_by(FileModel.created_at.asc())
            .first()
        )
        if not next_file:
            db.commit()
            return {"dispatched": False, "file_id": None, "reason": "kolejka pusta"}

        webhook_url = _get_webhook_url(db)
        if not webhook_url:
            db.commit()
            logger.error("[DISPATCH] Brak N8N webhook URL — kolejka wstrzymana")
            return {"dispatched": False, "file_id": next_file.id,
                    "reason": "brak skonfigurowanego webhook URL"}

        # Zajmij slot: PROCESSING + commit (zwalnia blokadę). Od tej chwili inne
        # instancje widzą in_flight > 0 i nie wyślą kolejnego pliku.
        payload = _build_payload(next_file)
        file_id, filename = next_file.id, next_file.filename
        next_file.status = DocumentStatus.PROCESSING
        db.commit()
    except Exception:
        db.rollback()
        raise
    # ===== Koniec sekcji krytycznej — blokada zwolniona =====

    logger.info(f"[DISPATCH] Wysyłam plik {file_id} ({filename}) do n8n: {webhook_url}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload, headers=outgoing_headers())
    except httpx.RequestError as e:
        # Awaria PRZEJŚCIOWA: n8n nieosiągalny (zatrzymany, timeout, sieć).
        # Nie palimy pliku na ERROR — wraca do kolejki i zostanie ponowiony.
        logger.warning(
            f"[DISPATCH] n8n nieosiągalny dla pliku {file_id}: {e} — "
            f"wracam do PENDING (ponowię później)"
        )
        _revert_to_pending(db, file_id)
        return {"dispatched": False, "file_id": file_id,
                "reason": f"n8n nieosiągalny: {e}", "retry": True}
    except Exception as e:
        # Nieoczekiwany błąd — traktujemy jako trwały.
        logger.error(f"[DISPATCH] Plik {file_id}: nieoczekiwany wyjątek: {e}")
        _mark_error(db, file_id, reason=f"Nieoczekiwany błąd wysyłki: {e}")
        return {"dispatched": False, "file_id": file_id, "reason": str(e)}

    if resp.status_code == 200:
        logger.info(f"[DISPATCH] Plik {file_id} przekazany do n8n (status PROCESSING)")
        return {"dispatched": True, "file_id": file_id, "reason": "ok"}

    # Awaria TRWAŁA: n8n odpowiedział, ale błędem (np. 4xx/5xx workflow).
    err = f"Webhook zwrócił {resp.status_code}: {resp.text[:300]}"
    logger.error(f"[DISPATCH] Plik {file_id}: {err}")
    _mark_error(db, file_id, reason=err)
    return {"dispatched": False, "file_id": file_id, "reason": err}
