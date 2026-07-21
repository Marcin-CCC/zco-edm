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

Uwaga: statusu PROCESSING NIE ustawia dyspozytor — robi to workflow n8n
przez PATCH (nod "Status PROCESSING sending"). Dyspozytor traktuje jednak
plik wysłany do n8n jako "zajmujący slot" poprzez znacznik in-flight w DB?
Nie — prościej: dyspozytor ustawia status PROCESSING sam, natychmiast po
udanym wywołaniu webhooka. Nod PROCESSING w n8n jest wtedy idempotentny
(nadpisuje tym samym statusem). Dzięki temu stan kolejki żyje wyłącznie
w kolumnie files.status i przeżywa restart backendu.
"""

import os
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.models import File as FileModel, DocumentStatus
from app.n8n_auth import outgoing_headers

logger = logging.getLogger(__name__)

# Po ilu minutach plik wiszący w PROCESSING uznajemy za martwy (watchdog)
PROCESSING_TIMEOUT_MINUTES = int(os.getenv("PROCESSING_TIMEOUT_MINUTES", "30"))


def _get_webhook_url(db: Session) -> str | None:
    """Webhook URL z ustawień aplikacji (DB) z fallbackiem na env."""
    from app.settings.router import _load_cache_from_db, get_webhook_url
    _load_cache_from_db(db)
    return get_webhook_url()


def _build_payload(file: FileModel) -> dict:
    from app.files.router import build_webhook_payload
    return build_webhook_payload(file.id, file.file_path)


def _reap_stale_processing(db: Session) -> None:
    """Watchdog: oznacz jako ERROR pliki wiszące w PROCESSING zbyt długo."""
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
    if stale:
        db.commit()


async def try_dispatch_next(db: Session) -> dict:
    """Uruchom przetwarzanie następnego pliku, jeśli nic się nie przetwarza.

    Zwraca słownik diagnostyczny:
      {"dispatched": bool, "file_id": int|None, "reason": str}
    """
    _reap_stale_processing(db)

    # Czy coś się już przetwarza? (1 plik naraz)
    in_flight = (
        db.query(FileModel)
        .filter(FileModel.status == DocumentStatus.PROCESSING)
        .count()
    )
    if in_flight > 0:
        return {"dispatched": False, "file_id": None,
                "reason": f"{in_flight} plik(ów) w trakcie przetwarzania"}

    # Najstarszy oczekujący
    next_file = (
        db.query(FileModel)
        .filter(FileModel.status == DocumentStatus.PENDING)
        .order_by(FileModel.created_at.asc())
        .first()
    )
    if not next_file:
        return {"dispatched": False, "file_id": None, "reason": "kolejka pusta"}

    webhook_url = _get_webhook_url(db)
    if not webhook_url:
        logger.error("[DISPATCH] Brak N8N webhook URL — kolejka wstrzymana")
        return {"dispatched": False, "file_id": next_file.id,
                "reason": "brak skonfigurowanego webhook URL"}

    payload = _build_payload(next_file)
    logger.info(f"[DISPATCH] Wysyłam plik {next_file.id} ({next_file.filename}) do n8n: {webhook_url}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload, headers=outgoing_headers())
        if resp.status_code == 200:
            # Zajmij slot — n8n i tak nadpisze PROCESSING przez PATCH (idempotentne)
            next_file.status = DocumentStatus.PROCESSING
            db.commit()
            logger.info(f"[DISPATCH] Plik {next_file.id} przekazany do n8n (status PROCESSING)")
            return {"dispatched": True, "file_id": next_file.id, "reason": "ok"}
        else:
            err = f"Webhook zwrócił {resp.status_code}: {resp.text[:300]}"
            logger.error(f"[DISPATCH] Plik {next_file.id}: {err}")
            next_file.status = DocumentStatus.ERROR
            db.commit()
            return {"dispatched": False, "file_id": next_file.id, "reason": err}
    except Exception as e:
        logger.error(f"[DISPATCH] Plik {next_file.id}: wyjątek wywołania webhooka: {e}")
        next_file.status = DocumentStatus.ERROR
        db.commit()
        return {"dispatched": False, "file_id": next_file.id, "reason": str(e)}
