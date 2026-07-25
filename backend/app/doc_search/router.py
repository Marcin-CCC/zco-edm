"""Wyszukiwanie po polach strukturalnych dokumentów (#7B-2).

Parsowanie zapisuje w `files.metadata_` typ dokumentu i wartości pól nagłówkowych:
    metadata_ = { ..., "doc_type": "zarzadzenie",
                  "doc_fields": {"data": "2023-04-07", "numer_dokumentu": "8/2023"} }

Ten endpoint pozwala je przeszukać (SQL po JSON w Postgresie), np. „wszystkie
zarządzenia z 2023" albo „dokumenty, gdzie dostawca = X". Filtr jest STRUKTURALNY
(typ + warunki na polach) — warstwę NL→filtr (pytanie po polsku → ten filtr)
dołożymy nad tym później. Wyniki są ograniczone RBAC-iem roli (jak w czacie):
użytkownik widzi tylko dokumenty z folderów, do których ma dostęp.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import User, File as FileModel
from app.rbac import readable_folder_ids

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/doc-search", tags=["DocSearch"])

_ALLOWED_OPS = {"eq", "contains", "gte", "lte"}


class FieldFilter(BaseModel):
    field: str
    op: str = "contains"          # eq | contains | gte | lte
    value: str


class SearchRequest(BaseModel):
    doc_type: Optional[str] = None
    filters: list[FieldFilter] = []
    limit: int = 100


class SearchHit(BaseModel):
    id: int
    filename: str
    folder_id: Optional[int] = None
    doc_type: Optional[str] = None
    fields: dict = {}


@router.post("", response_model=list[SearchHit])
def search_documents(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Znajdź dokumenty po typie i wartościach pól (SQL po metadata_)."""
    q = db.query(FileModel).filter(FileModel.metadata_.isnot(None))

    # Typ dokumentu (metadata->>'doc_type')
    if payload.doc_type:
        q = q.filter(FileModel.metadata_["doc_type"].astext == payload.doc_type.strip())

    # Warunki na polach (metadata->'doc_fields'->>'<field>')
    for f in payload.filters:
        op = (f.op or "contains").lower()
        if op not in _ALLOWED_OPS:
            raise HTTPException(status_code=400, detail=f"Nieobsługiwany operator: {f.op}")
        if not f.field.strip():
            continue
        col = FileModel.metadata_["doc_fields"][f.field.strip()].astext
        val = f.value.strip()
        if op == "eq":
            q = q.filter(func.lower(col) == val.lower())
        elif op == "contains":
            q = q.filter(col.ilike(f"%{val}%"))
        elif op == "gte":
            q = q.filter(col >= val)
        elif op == "lte":
            q = q.filter(col <= val)

    # RBAC: tylko foldery czytelne dla roli (admin: readable is None → bez filtra)
    readable = readable_folder_ids(current_user, db)
    if readable is not None:
        if not readable:
            return []
        q = q.filter(FileModel.folder_id.in_(sorted(readable)))

    limit = min(max(payload.limit, 1), 500)
    files = q.order_by(FileModel.id.desc()).limit(limit).all()

    hits = []
    for f in files:
        meta = f.metadata_ or {}
        hits.append(SearchHit(
            id=f.id,
            filename=f.filename,
            folder_id=f.folder_id,
            doc_type=meta.get("doc_type"),
            fields=meta.get("doc_fields") or {},
        ))
    return hits
