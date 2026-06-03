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
from app.models import File as FileModel, DocumentStatus
from app.files.router import get_mime_type

router = APIRouter(prefix="/api/webhook", tags=["Webhooks"])


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
        # Jeśli istnieje i ma status PROCESSED, zignoruj
        if existing.status == DocumentStatus.PROCESSED:
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
        uploaded_by=0,  # system upload (n8n)
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
async def update_file_status(file_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
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

    # Aktualizuj status
    file_obj.status = payload.status

    # Aktualizuj OCR wynik
    if payload.ocr_result:
        file_obj.ocr_result = payload.ocr_result

    # Aktualizuj metadane
    if payload.metadata:
        file_obj.metadata = payload.metadata

    db.commit()

    return {
        "file_id": file_id,
        "status": file_obj.status,
        "message": "Status zaktualizowany"
    }