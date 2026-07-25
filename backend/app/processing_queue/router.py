"""Processing Queue Router - endpointy dla kolejki przetwarzania."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
import httpx

from app.database import get_db
from app.models import ProcessingQueue, Document, File as FileModel, DocumentStatus, UserRole
from app.auth.auth import get_current_user
from app.config import settings
from app.settings.router import get_webhook_url, _load_cache_from_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/processing-queue", tags=["Processing Queue"])


@router.get("/")
def list_processing_queue(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List processing queue items with document info."""
    query = db.query(ProcessingQueue).join(Document, isouter=True)
    if status:
        query = query.filter(ProcessingQueue.status == status)
    items = query.order_by(ProcessingQueue.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for item in items:
        result.append({
            "id": item.id,
            "document_id": item.document_id,
            "file_name": item.document.filename if item.document else "unknown",
            "status": item.status,
            "page_count": item.document.chunks_count if item.document else 0,
            "error_message": item.error_message,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.created_at.isoformat() if item.created_at else None,
            "started_at": item.started_at.isoformat() if item.started_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        })
    return result


@router.get("/{item_id}")
def get_processing_queue_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get single processing queue item."""
    item = db.query(ProcessingQueue).filter(ProcessingQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element kolejki nie istnieje.")

    return {
        "id": item.id,
        "document_id": item.document_id,
        "file_name": item.document.filename if item.document else "unknown",
        "status": item.status,
        "page_count": item.document.chunks_count if item.document else 0,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.created_at.isoformat() if item.created_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


@router.post("/{file_id}/retry")
async def retry_processing(
    file_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Retry processing for a file.

    Ustawia status PENDING (wraca do kolejki) i uruchamia dyspozytor —
    jeśli nic się nie przetwarza, plik ruszy od razu; w przeciwnym razie
    poczeka na swoją kolej (1 plik naraz).
    """
    logger.info(f"[RETRY] Retry called for file_id={file_id}, user={current_user.username if current_user else 'unknown'}")

    # Find the file in the files table
    file = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file:
        logger.warning(f"[RETRY] File {file_id} not found")
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    logger.info(f"[RETRY] Found file: {file.filename}, current status: {file.status}")

    # Wróć do kolejki i wyczyść stary powód błędu (żeby UI nie pokazywało nieświeżego)
    file.status = DocumentStatus.PENDING
    if isinstance(file.metadata_, dict) and "error" in file.metadata_:
        cleaned = dict(file.metadata_)
        cleaned.pop("error", None)
        file.metadata_ = cleaned
    db.commit()

    # Uruchom dyspozytor (wyśle webhook jeśli slot wolny)
    from app.dispatcher import try_dispatch_next
    dispatch_result = await try_dispatch_next(db)
    db.refresh(file)
    logger.info(f"[RETRY] File {file_id} -> PENDING; dispatch: {dispatch_result}")

    if file.status == DocumentStatus.ERROR:
        return {
            "message": dispatch_result.get("reason", "Nie udało się uruchomić przetwarzania."),
            "file_id": file.id,
            "filename": file.filename,
            "error": True,
        }

    message = (
        "Przetwarzanie uruchomione."
        if dispatch_result.get("file_id") == file.id and dispatch_result.get("dispatched")
        else "Plik wrócił do kolejki i czeka na swoją kolej."
    )
    return {"message": message, "file_id": file.id, "filename": file.filename, "dispatch": dispatch_result}


@router.post("/{file_id}/reparse")
async def reparse_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """TESTOWE (#7B-2, strojenie klasyfikacji): przetwórz plik OD NOWA z wyczyszczeniem
    wektorów. Kasuje wektory pliku z Qdranta (bez duplikatów przy ponownym parsowaniu),
    czyści wynik klasyfikacji/parsowania i status → PENDING, uruchamia dyspozytor.

    Docelowo do usunięcia — przycisk włączony tylko na czas testów klasyfikacji.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Tylko administrator.")

    file = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="Plik nie istnieje.")

    # 1) Skasuj wektory pliku (uniknij duplikatów w Qdrancie przy ponownym parsowaniu)
    from app.qdrant_client import delete_vectors_by_file_id
    delete_vectors_by_file_id(file_id)

    # 2) Wyczyść wynik klasyfikacji/parsowania i ewentualny błąd
    if isinstance(file.metadata_, dict):
        cleaned = dict(file.metadata_)
        for k in ("doc_type", "doc_fields", "doc_type_verified", "error", "processing_seconds", "processing_started_at"):
            cleaned.pop(k, None)
        file.metadata_ = cleaned
    file.ocr_result = None
    file.status = DocumentStatus.PENDING
    db.commit()

    # 3) Uruchom dyspozytor (wyśle plik do parsowania, jeśli slot wolny)
    from app.dispatcher import try_dispatch_next
    dispatch = await try_dispatch_next(db)
    db.refresh(file)
    logger.info(f"[REPARSE] Plik {file_id} → PENDING (wektory skasowane); dispatch: {dispatch}")
    return {
        "message": "Plik skierowany do ponownego przetwarzania (wektory skasowane).",
        "file_id": file_id,
        "filename": file.filename,
        "dispatch": dispatch,
    }


@router.post("/{item_id}/skip-page")
def skip_page(
    item_id: int,
    page_number: int = Query(..., ge=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Skip a specific page in processing."""
    item = db.query(ProcessingQueue).filter(ProcessingQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element kolejki nie istnieje.")

    # Mark the page as skipped in the document
    if item.document:
        item.document.raw_text = item.document.raw_text or ""
        # Note: In a real implementation, you'd track skipped pages separately
        item.status = "skipped_page"
        db.commit()
        db.refresh(item)

    return {"message": f"Strona {page_number} pominięta."}
