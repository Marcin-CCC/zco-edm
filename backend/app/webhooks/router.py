"""
Webhook router dla n8n.

Endpointy:
- POST /api/webhook/file-notified — n8n informuje backend o nowym pliku
- PATCH /api/webhook/file/{file_id}/status — n8n aktualizuje status pliku
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import File as FileModel, DocumentStatus, User, UserRole
from app.files.router import get_mime_type
from app.webhook_auth import verify_webhook_secret

# Cały router jest wywoływany przez n8n (nie przez przeglądarkę), więc zamiast
# JWT chroni go wspólny sekret w nagłówku X-Webhook-Secret.
router = APIRouter(
    prefix="/api/webhook",
    tags=["Webhooks"],
    dependencies=[Depends(verify_webhook_secret)],
)


def _resolve_status(value: str) -> DocumentStatus:
    """Map an incoming status string (enum name or value, PL/EN) to DocumentStatus."""
    if isinstance(value, DocumentStatus):
        return value
    # Try enum name (e.g. "PENDING", "READY")
    normalized = value.strip()
    if normalized.upper() in DocumentStatus.__members__:
        return DocumentStatus[normalized.upper()]
    # Try enum value (e.g. "Przetworzono", "W kolejce (n8n)")
    for member in DocumentStatus:
        if member.value == normalized:
            return member
    # Legacy aliases used by n8n (old pipeline stage names map to PROCESSING)
    aliases = {
        "PROCESSED": DocumentStatus.READY,
        "PRZETWARZANIE": DocumentStatus.PROCESSING,
        "PARSOWANIE (DOCLING)": DocumentStatus.PROCESSING,
        "CHUNKOWANIE": DocumentStatus.PROCESSING,
        "WEKTORYZACJA (QDRANT)": DocumentStatus.PROCESSING,
        "PARSING": DocumentStatus.PROCESSING,
        "PENDING_CHUNKING": DocumentStatus.PROCESSING,
        "PENDING_VECTORIZE": DocumentStatus.PROCESSING,
    }
    if normalized.upper() in aliases:
        return aliases[normalized.upper()]
    raise HTTPException(
        status_code=400,
        detail=f"Nieznany status: '{value}'. Dozwolone: "
               f"{[m.name for m in DocumentStatus]} lub {[m.value for m in DocumentStatus]}"
    )


def _get_system_user_id(db: Session) -> int:
    """Return id of the 'system' user (used for files registered by n8n)."""
    user = db.query(User).filter(User.username == "system").first()
    if user:
        return user.id
    # Fallback: first admin account
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if admin:
        return admin.id
    raise HTTPException(
        status_code=500,
        detail="Brak użytkownika systemowego ('system') — uruchom seed.sql."
    )


class FileNotification(BaseModel):
    """Powiadomienie o nowym pliku od n8n."""
    file_path: str  # pełna ścieżka do pliku na Sparku, np /home/marcin/zco-edm-app/shared_docs/uploads/umowa.pdf


class StatusUpdate(BaseModel):
    """Aktualizacja statusu pliku od n8n."""
    status: str = "PENDING"  # PENDING, PROCESSING, PROCESSED, ERROR
    ocr_result: str = None  # wynik OCR (markdown)
    metadata: dict = None  # dodatkowe metadane


@router.post("/file-notified")
async def file_notified(payload: FileNotification, db: Session = Depends(get_db)):
    """
    n8n informuje backend o nowym pliku.
    
    Backend tworzy rekord w bazie danych ze statusem PENDING.
    n8n samodzielnie przetwarza plik (Docling OCR, LLM analysis, etc.)
    i później aktualizuje status через PATCH /api/webhook/file/{id}/status
    """
    # Sprawdź czy plik istnieje
    if not os.path.exists(payload.file_path):
        raise HTTPException(status_code=404, detail=f"Brak pliku: {payload.file_path}")

    # Sprawdź czy rekord już istnieje
    existing = db.query(FileModel).filter(FileModel.file_path == payload.file_path).first()
    if existing:
        # Jeśli istnieje i ma status READY (Przetworzono), zignoruj
        if existing.status == DocumentStatus.READY:
            return {"file_id": existing.id, "status": existing.status, "message": "Plik juz przetworzony"}
        # Jeśli jest w trakcie przetwarzania, zaktualizuj status
        existing.status = DocumentStatus.PENDING
        db.commit()
        return {"file_id": existing.id, "status": "PENDING", "message": "Reuaktywacja pliku"}

    # Utwórz nowy rekord
    db_file = FileModel(
        filename=os.path.basename(payload.file_path),
        file_path=payload.file_path,
        mime_type=get_mime_type(payload.file_path),
        size=os.path.getsize(payload.file_path),
        status=DocumentStatus.PENDING,
        uploaded_by=_get_system_user_id(db),  # system upload (n8n)
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return {
        "file_id": db_file.id,
        "filename": db_file.filename,
        "file_path": db_file.file_path,
        "status": db_file.status,
        "message": "Plik zarejestrowany"
    }


@router.patch("/file/{file_id}/status")
async def update_file_status(file_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):  # noqa: C901
    """
    n8n aktualizuje status pliku po przetworzeniu.
    
    Moze zaktualizowac:
    - status: PENDING → PROCESSING → PROCESSED / ERROR
    - ocr_result: wynik z Docling (markdown)
    - metadata: dodatkowe dane (np. wyniki analizy LLM)
    """
    file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="Plik nie znaleziony")

    # Aktualizuj status (mapowanie stringa na DocumentStatus)
    new_status = _resolve_status(payload.status)
    file_obj.status = new_status

    # Aktualizuj OCR wynik
    if payload.ocr_result:
        file_obj.ocr_result = payload.ocr_result

    # Aktualizuj metadane — SCAL z istniejącymi (nie nadpisuj całości).
    # n8n przy błędzie może przysłać {"error": "..."} → trafia do UI kolejki.
    if payload.metadata:
        merged = dict(file_obj.metadata_ or {})
        merged.update(payload.metadata)
        file_obj.metadata_ = merged

    # Sukces kasuje ewentualny stary błąd (np. po ponowieniu wcześniejszej awarii)
    if new_status == DocumentStatus.READY and isinstance(file_obj.metadata_, dict):
        if "error" in file_obj.metadata_:
            cleaned = dict(file_obj.metadata_)
            cleaned.pop("error", None)
            file_obj.metadata_ = cleaned

    # Czas parsowania: przy statusie terminalnym policz sekundy od startu (PROCESSING)
    if new_status in (DocumentStatus.READY, DocumentStatus.ERROR):
        from app.dispatcher import mark_processing_finished
        mark_processing_finished(file_obj)

    db.commit()

    # >>> Kolejka: po zakończeniu przetwarzania uruchom następny plik <<<
    dispatch_info = None
    if new_status in (DocumentStatus.READY, DocumentStatus.ERROR):
        from app.dispatcher import try_dispatch_next
        import logging
        dispatch_info = await try_dispatch_next(db)
        logging.getLogger(__name__).info(
            f"[WEBHOOK] Plik {file_id} zakończony ({new_status.name}); dispatch: {dispatch_info}"
        )
    # <<< END kolejka >>>

    return {
        "file_id": file_id,
        "status": file_obj.status.value if hasattr(file_obj.status, "value") else str(file_obj.status),
        "message": "Status zaktualizowany",
        "dispatch": dispatch_info,
    }