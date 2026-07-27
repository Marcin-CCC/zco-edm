"""Wyszukiwanie po polach strukturalnych dokumentów (#7B-2).

Parsowanie zapisuje w `files.metadata_` typ dokumentu i wartości pól nagłówkowych:
    metadata_ = { ..., "doc_type": "zarzadzenie",
                  "doc_fields": {"data": "2023-04-07", "numer_dokumentu": "8/2023"} }

Dwa wejścia:
- POST ""     — filtr STRUKTURALNY (typ + warunki na polach) z formularza.
- POST "/nl"  — pytanie po polsku → LLM zamienia je na ten sam filtr (NL→filtr).

Oba używają tej samej logiki SQL (`_run_search`) po JSON w Postgresie i tego samego
RBAC-u roli (użytkownik widzi tylko dokumenty z dozwolonych folderów).
"""
import calendar
import json
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import User, File as FileModel
from app.rbac import readable_folder_ids
from app.config import settings
from app.doc_schemas.router import get_active_schemas

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/doc-search", tags=["DocSearch"])

_ALLOWED_OPS = {"eq", "contains", "gte", "lte"}
_NL_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

_YEAR_RE = re.compile(r"^\d{4}$")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{1,2}$")


def _expand_date_bound(value: str, op: str) -> str:
    """Rozwiń „rok" / „rok-miesiąc" do pełnej daty granicznej.

    Porównania idą po TEKŚCIE, więc `data <= '2023'` nie łapie '2023-04-07'
    (dłuższy napis o tym samym prefiksie jest większy) — przez to pytania
    „w roku 2023" dawały 0 wyników. Rozwijamy więc granice:
      gte 2023    → 2023-01-01     lte 2023    → 2023-12-31
      gte 2023-04 → 2023-04-01     lte 2023-04 → 2023-04-30
    Wartości pełnych dat zostawiamy bez zmian.
    """
    if _YEAR_RE.match(value):
        return f"{value}-01-01" if op == "gte" else f"{value}-12-31"
    if _YEAR_MONTH_RE.match(value):
        year, month = value.split("-")
        month_i = int(month)
        if not 1 <= month_i <= 12:
            return value
        norm = f"{int(year):04d}-{month_i:02d}"
        if op == "gte":
            return f"{norm}-01"
        return f"{norm}-{calendar.monthrange(int(year), month_i)[1]:02d}"
    return value


class FieldFilter(BaseModel):
    field: str
    op: str = "contains"          # eq | contains | gte | lte
    value: str


class SearchRequest(BaseModel):
    doc_type: Optional[str] = None
    filters: list[FieldFilter] = []
    limit: int = 100


class NLSearchRequest(BaseModel):
    query: str
    limit: int = 100


class SearchHit(BaseModel):
    id: int
    filename: str
    folder_id: Optional[int] = None
    doc_type: Optional[str] = None
    fields: dict = {}


def _run_search(
    db: Session,
    current_user: User,
    doc_type: Optional[str],
    filters: list[FieldFilter],
    limit: int = 100,
) -> list[SearchHit]:
    """Wspólna logika: filtr strukturalny → SQL po metadata_ + RBAC roli."""
    q = db.query(FileModel).filter(FileModel.metadata_.isnot(None))

    # Typ dokumentu (metadata->>'doc_type'). Kolumna to generic JSON (nie JSONB),
    # więc `.astext` nie działa — używamy operatorów PostgreSQL ->/->> przez .op().
    if doc_type:
        q = q.filter(FileModel.metadata_.op("->>")("doc_type") == doc_type.strip())

    # Warunki na polach (metadata->'doc_fields'->>'<field>')
    for f in filters:
        op = (f.op or "contains").lower()
        if op not in _ALLOWED_OPS or not f.field.strip():
            continue
        col = FileModel.metadata_.op("->")("doc_fields").op("->>")(f.field.strip())
        val = f.value.strip()
        if op == "eq":
            q = q.filter(func.lower(col) == val.lower())
        elif op == "contains":
            q = q.filter(col.ilike(f"%{val}%"))
        elif op == "gte":
            q = q.filter(col >= _expand_date_bound(val, "gte"))
        elif op == "lte":
            q = q.filter(col <= _expand_date_bound(val, "lte"))

    # RBAC: tylko foldery czytelne dla roli (admin: readable is None → bez filtra)
    readable = readable_folder_ids(current_user, db)
    if readable is not None:
        if not readable:
            return []
        q = q.filter(FileModel.folder_id.in_(sorted(readable)))

    limit = min(max(limit, 1), 500)
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


@router.post("", response_model=list[SearchHit])
def search_documents(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Znajdź dokumenty po typie i wartościach pól (filtr strukturalny z formularza)."""
    for f in payload.filters:
        if (f.op or "contains").lower() not in _ALLOWED_OPS:
            raise HTTPException(status_code=400, detail=f"Nieobsługiwany operator: {f.op}")
    return _run_search(db, current_user, payload.doc_type, payload.filters, payload.limit)


# ==================== NL → filtr ====================
def _nl_response_format(schemas: list[dict]) -> dict:
    slugs = [s["slug"] for s in schemas] + [""]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "filtr_wyszukiwania",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "doc_type": {"type": "string", "enum": slugs},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string", "enum": ["eq", "contains", "gte", "lte"]},
                                "value": {"type": "string"},
                            },
                            "required": ["field", "op", "value"],
                        },
                    },
                },
                "required": ["doc_type", "filters"],
            },
        },
    }


async def _nl_to_filter(query: str, schemas: list[dict]) -> dict:
    """Zamień pytanie po polsku na filtr {doc_type, filters[]} (LLM, guided decoding)."""
    lines = ["KATALOG TYPÓW DOKUMENTÓW:"]
    for s in schemas:
        fields = ", ".join(f.get("name") for f in (s.get("fields") or [])) or "—"
        lines.append(f"- slug: {s['slug']} | nazwa: {s.get('name', s['slug'])} | pola: {fields}")
    catalog = "\n".join(lines)
    system = (
        "Zamieniasz pytanie użytkownika na filtr wyszukiwania dokumentów. Masz katalog "
        "typów i ich pól. Ustaw doc_type (slug) TYLKO jeśli pytanie wyraźnie wskazuje typ; "
        "w przeciwnym razie doc_type=\"\". Dodaj warunki na polach (nazwa pola DOKŁADNIE z "
        "katalogu wybranego typu, operator, wartość). Operatory: eq (równe), contains "
        "(zawiera), gte (od/większe-równe), lte (do/mniejsze-równe). Dla zakresów dat użyj "
        "gte i/lub lte (wartości jako tekst, np. 2023 albo 2023-04). Nie wymyślaj pól "
        "spoza katalogu. Zwróć wyłącznie JSON zgodny ze schematem."
    )
    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{catalog}\n\nPYTANIE: {query}"},
        ],
        "response_format": _nl_response_format(schemas),
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_NL_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


@router.post("/nl")
async def nl_search(
    payload: NLSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pytanie po polsku → filtr (LLM) → wyszukiwanie. Zwraca rozpoznany filtr + wyniki."""
    schemas = get_active_schemas(db)
    if not (payload.query or "").strip():
        raise HTTPException(status_code=400, detail="Puste zapytanie.")

    try:
        parsed = await _nl_to_filter(payload.query.strip(), schemas)
    except Exception as e:
        logger.warning(f"[DOC-SEARCH-NL] Rozpoznanie filtra nieudane: {e}")
        raise HTTPException(status_code=502, detail="Nie udało się zrozumieć zapytania.")

    valid_slugs = {s["slug"] for s in schemas}
    doc_type = (parsed.get("doc_type") or "").strip() or None
    if doc_type and doc_type not in valid_slugs:
        doc_type = None

    # Pola dozwolone dla wybranego typu (odsiej wymyślone przez model)
    allowed_fields = set()
    if doc_type:
        for s in schemas:
            if s["slug"] == doc_type:
                allowed_fields = {f.get("name") for f in (s.get("fields") or [])}
                break

    filters: list[FieldFilter] = []
    for f in (parsed.get("filters") or []):
        field = (f.get("field") or "").strip()
        value = (f.get("value") or "").strip()
        op = (f.get("op") or "contains").lower()
        if not field or not value:
            continue
        if op not in _ALLOWED_OPS:
            op = "contains"
        if allowed_fields and field not in allowed_fields:
            continue
        filters.append(FieldFilter(field=field, op=op, value=value))

    hits = _run_search(db, current_user, doc_type, filters, payload.limit)
    return {
        "filter": {"doc_type": doc_type, "filters": [f.model_dump() for f in filters]},
        "hits": [h.model_dump() for h in hits],
    }
