"""
Rejestr schematów typów dokumentów (#7B-2).

Jeden wpis = jeden typ dokumentu (slug, nazwa, kryteria klasyfikacji, lista pól).
Z rejestru wynikają: prompt klasyfikacji, prompt ekstrakcji, walidacja pól przy
zapisie oraz tłumaczenie NL→filtr. Dodanie nowego typu = nowy wiersz (bez deployu).

Konsumenci:
- n8n (parsowanie): dostaje aktywne schematy w payloadzie dispatchu (nie przez
  ten endpoint) — patrz dispatcher; tutaj admin nimi zarządza.
- backend (NL→filtr): czyta rejestr bezpośrednio z DB (get_active_schemas).
- admin UI (docelowo): CRUD przez te endpointy.
"""
import re
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import User, DocTypeSchema
from app.schemas import DocTypeSchemaBase, DocTypeSchemaResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/doc-schemas", tags=["DocSchemas"])

_SLUG_RE = re.compile(r"^[a-z0-9_-]{2,50}$")
_ALLOWED_FIELD_TYPES_PREFIX = ("string", "number", "date", "enum:")


def get_active_schemas(db: Session) -> list[dict]:
    """Aktywne schematy jako listy dictów — dla dispatchera (payload n8n) i NL→filtr."""
    rows = db.query(DocTypeSchema).filter(DocTypeSchema.active.is_(True)).all()
    result = []
    for r in rows:
        result.append({
            "slug": r.slug,
            "name": r.name,
            "criteria": r.criteria or "",
            "fields": r.fields or [],
        })
    return result


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def _validate_name_pattern(pattern: str | None, fields: list) -> str | None:
    """Wzorzec nazwy pliku dla tego typu; ``None`` gdy pusty.

    Sprawdzamy placeholdery od razu przy zapisie, bo literówka („{numer_dok}"
    zamiast „{numer}") objawiłaby się dopiero przy próbie nadania nazw, jako
    „brak pól" przy każdym dokumencie — czyli w miejscu, gdzie nikt jej nie szuka.
    """
    wzorzec = (pattern or "").strip()
    if not wzorzec:
        return None
    znane = {f.name for f in fields} | {"typ"}
    uzyte = set(_PLACEHOLDER_RE.findall(wzorzec))
    if not uzyte:
        raise HTTPException(
            status_code=400,
            detail="Wzorzec nazwy musi zawierać choć jedno pole w nawiasach, np. {typ}-{numer}.",
        )
    nieznane = sorted(uzyte - znane)
    if nieznane:
        raise HTTPException(
            status_code=400,
            detail=("Wzorzec używa pól, których ten typ nie ma: "
                    + ", ".join(nieznane)
                    + ". Dostępne: " + ", ".join(sorted(znane)) + "."),
        )
    return wzorzec


def _validate_fields(fields: list) -> None:
    for f in fields:
        t = (f.type or "").strip()
        if not any(t == p or t.startswith("enum:") for p in _ALLOWED_FIELD_TYPES_PREFIX):
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy typ pola '{f.name}': '{t}'. Dozwolone: string|number|date|enum:v1,v2,...",
            )


@router.get("", response_model=list[DocTypeSchemaResponse])
def list_schemas(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista schematów. Domyślnie tylko aktywne."""
    q = db.query(DocTypeSchema)
    if not include_inactive:
        q = q.filter(DocTypeSchema.active.is_(True))
    return q.order_by(DocTypeSchema.slug).all()


@router.post("", response_model=DocTypeSchemaResponse)
def upsert_schema(
    payload: DocTypeSchemaBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Utwórz lub zaktualizuj schemat (po slugu). Tylko admin.

    Dzięki upsertowi zatwierdzone schematy dodaje się/aktualizuje bez deployu.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zarządzać schematami.")

    slug = (payload.slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="slug: 2–50 znaków [a-z0-9_-].")
    _validate_fields(payload.fields)

    fields_data = [f.model_dump() for f in payload.fields]
    wzorzec = _validate_name_pattern(payload.name_pattern, payload.fields)
    existing = db.query(DocTypeSchema).filter(DocTypeSchema.slug == slug).first()
    if existing:
        existing.name = payload.name
        existing.criteria = payload.criteria
        existing.fields = fields_data
        existing.name_pattern = wzorzec
        existing.active = payload.active
        db.commit()
        db.refresh(existing)
        logger.info(f"[DOC-SCHEMAS] Zaktualizowano schemat '{slug}'")
        return existing

    new = DocTypeSchema(
        slug=slug, name=payload.name, criteria=payload.criteria,
        fields=fields_data, name_pattern=wzorzec, active=payload.active,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    logger.info(f"[DOC-SCHEMAS] Dodano schemat '{slug}'")
    return new


@router.delete("/{slug}")
def delete_schema(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuń schemat (po slugu). Tylko admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Tylko administrator może zarządzać schematami.")
    row = db.query(DocTypeSchema).filter(DocTypeSchema.slug == slug.strip().lower()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Schemat nie istnieje.")
    db.delete(row)
    db.commit()
    return {"message": "Schemat usunięty.", "slug": slug}
