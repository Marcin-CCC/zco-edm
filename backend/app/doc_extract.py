"""Klasyfikacja typu dokumentu i ekstrakcja pól nagłówkowych (#7B-2).

Uruchamiane PO sparsowaniu pliku (callback READY). Tekst dokumentu odczytujemy
z Qdranta (chunki po file_id), a nie z parsowania — dzięki temu działa jednolicie
dla pdf/docx/xlsx i nie wymaga zmian w workflow n8n.

Przepływ:
1. Odczytaj początek tekstu dokumentu z Qdranta.
2. Zbuduj prompt z AKTYWNEGO rejestru schematów (katalog typów + pola).
3. Jedno wywołanie vLLM (guided decoding) → {doc_type, fields[]}.
4. Zapisz do files.metadata_: {"doc_type": ..., "doc_fields": {...}}.
5. Zwolnij flagę ekstrakcji i wznów kolejkę (dyspozytor był wstrzymany).

Arbitraż modelu: flagę `extraction_started()` podnosi wołający (handler READY)
SYNCHRONICZNIE, zanim odpali zadanie w tle — dzięki temu dyspozytor od razu widzi
zajętość i nie startuje kolejnego parsowania. Tu, w `finally`, flagę zwalniamy
i wołamy dyspozytora.
"""
import logging
import re
import unicodedata

import httpx

from app.config import settings
from app.activity import extraction_finished

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

# ==================== Dopasowanie nazw pól ====================
# Model zwraca nazwy pól „po swojemu": bez polskich znaków i ze spacjami zamienionymi
# na podkreślniki (schemat „kod procedury" → odpowiedź „kod_procedury", „opracował" →
# „opracowal"). Dosłowne porównanie odrzucało takie pola po cichu, więc dopasowujemy
# je w postaci kanonicznej i zapisujemy pod nazwą Z REJESTRU.
def _norm_key(name: str) -> str:
    s = (name or "").strip().lower().replace("ł", "l")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_\-]+", "", s)


def _canonical_fields(items: list, schema: dict) -> dict:
    """Zamień listę {name,value} od modelu na słownik z nazwami pól z rejestru."""
    by_norm = {
        _norm_key(f.get("name")): f.get("name")
        for f in (schema.get("fields") or []) if f.get("name")
    }
    out = {}
    for item in items or []:
        name, value = item.get("name"), item.get("value")
        if not name or not value:
            continue
        canon = by_norm.get(_norm_key(name))
        if by_norm and not canon:
            logger.info(f"[EXTRACT] Pominięto pole spoza schematu: {name!r}")
            continue
        out[canon or name] = value
    return out


# ==================== Normalizacja dat ====================
# Wartości pól typu `date` zapisujemy ZAWSZE jako YYYY-MM-DD. Bez tego filtrowanie
# zakresami nie działa (porównania idą po tekście), np. „19 stycznia 2026 r." nie
# daje się porównać z „2023". Model bywa niekonsekwentny, więc normalizujemy sami.
_PL_MONTHS = {
    "stycznia": 1, "styczeń": 1, "styczen": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4, "kwiecien": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpień": 8, "sierpien": 8,
    "września": 9, "wrzesnia": 9, "wrzesień": 9, "wrzesien": 9,
    "października": 10, "pazdziernika": 10, "październik": 10, "pazdziernik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12, "grudzien": 12,
}

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DOTTED_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$")
_PL_TEXT_RE = re.compile(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", re.IGNORECASE)


def normalize_date(value: str) -> str:
    """Sprowadź datę do YYYY-MM-DD. Gdy się nie da — zwróć wartość bez zmian."""
    if not value:
        return value
    v = str(value).strip()

    m = _ISO_RE.match(v)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}" if 1 <= mo <= 12 and 1 <= d <= 31 else v

    m = _DOTTED_RE.match(v)  # 11.12.2024 / 11-12-2024
    if m:
        d, mo, y = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}" if 1 <= mo <= 12 and 1 <= d <= 31 else v

    m = _PL_TEXT_RE.search(v)  # „19 stycznia 2026 r."
    if m:
        d, month_name, y = m.group(1), m.group(2).lower(), m.group(3)
        mo = _PL_MONTHS.get(month_name)
        if mo:
            return f"{int(y):04d}-{mo:02d}-{int(d):02d}"
    return v


def _normalize_fields(fields: dict, schema: dict) -> dict:
    """Znormalizuj pola typu `date` do YYYY-MM-DD; odrzuć wartości niebędące datą.

    Model potrafi wyciągnąć z formularza śmieć (np. linię kropek „…........"), a taka
    wartość przy porównaniu tekstowym wypada „po" każdej dacie i zaśmieca wyniki
    filtrowania po zakresach. Lepiej nie mieć pola niż mieć w nim nie-datę.
    """
    date_names = {
        f.get("name") for f in (schema.get("fields") or [])
        if (f.get("type") or "").strip().lower() == "date"
    }
    out = {}
    for k, v in fields.items():
        if k not in date_names:
            out[k] = v
            continue
        norm = normalize_date(v)
        if _ISO_RE.match(norm or ""):
            out[k] = norm
        else:
            logger.info(f"[EXTRACT] Odrzucono nie-datę w polu '{k}': {v!r}")
    return out


def _build_messages(schemas: list[dict], text: str, filename: str = "") -> list[dict]:
    lines = ["KATALOG TYPÓW DOKUMENTÓW:"]
    for s in schemas:
        fields = ", ".join(
            f"{f.get('name')} ({f.get('type', 'string')})" for f in (s.get("fields") or [])
        ) or "—"
        crit = (s.get("criteria") or "").strip()
        lines.append(f"- slug: {s['slug']} | nazwa: {s.get('name', s['slug'])}"
                     f"{(' | kryteria: ' + crit) if crit else ''} | pola: {fields}")
    catalog = "\n".join(lines)
    system = (
        "Jesteś klasyfikatorem dokumentów urzędowych. Dostajesz nazwę pliku, katalog "
        "typów (z kryteriami i polami) oraz początek dokumentu. Wybierz NAJLEPIEJ "
        "pasujący typ (jego slug). Nazwa pliku bywa mocną wskazówką co do typu "
        "(np. nazwa zaczynająca się od 'Załącznik nr' wskazuje na załącznik, a "
        "'Zarządzenie Nr' na zarządzenie), ale gdy treść wyraźnie przeczy nazwie, "
        "rozstrzyga treść. Jeśli żaden typ nie "
        "pasuje, użyj doc_type='inny'. Następnie wyciągnij wartości pól WYŁĄCZNIE dla "
        "wybranego typu (nazwy pól dokładnie jak w katalogu). Jeśli pola nie ma w "
        "dokumencie — pomiń je. Daty zwracaj w formacie YYYY-MM-DD. "
        "Zwróć wyłącznie JSON zgodny ze schematem."
    )
    user = f"NAZWA PLIKU: {filename}\n\n{catalog}\n\nDOKUMENT (początek):\n{text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _response_format(schemas: list[dict]) -> dict:
    slugs = [s["slug"] for s in schemas] + ["inny"]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "klasyfikacja_dokumentu",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "doc_type": {"type": "string", "enum": slugs},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["name", "value"],
                        },
                    },
                },
                "required": ["doc_type", "fields"],
            },
        },
    }


async def _classify(schemas: list[dict], text: str, filename: str = "") -> dict | None:
    """Jedno wywołanie vLLM. Zwraca {'doc_type', 'doc_fields'} albo None przy błędzie."""
    import json

    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 600,
        "messages": _build_messages(schemas, text, filename),
        "response_format": _response_format(schemas),
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    doc_type = (parsed.get("doc_type") or "").strip()
    chosen: dict = next((s for s in schemas if s["slug"] == doc_type), {})
    # Dopasuj nazwy pól do rejestru (odporne na odmiany zapisu) i odsiej szum modelu
    doc_fields = _canonical_fields(parsed.get("fields") or [], chosen)
    if chosen:
        doc_fields = _normalize_fields(doc_fields, chosen)  # daty → YYYY-MM-DD
    return {"doc_type": doc_type, "doc_fields": doc_fields}


def _extract_response_format(schema: dict) -> dict:
    """Guided schema do samej ekstrakcji pól narzuconego typu (nazwy pól = enum)."""
    names = [f.get("name") for f in (schema.get("fields") or []) if f.get("name")]
    name_prop = {"type": "string", "enum": names} if names else {"type": "string"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ekstrakcja_pol",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"name": name_prop, "value": {"type": "string"}},
                            "required": ["name", "value"],
                        },
                    }
                },
                "required": ["fields"],
            },
        },
    }


async def extract_fields(schema: dict, text: str, filename: str = "") -> dict:
    """Wyciągnij pola dla NARZUCONEGO typu (bez klasyfikacji) — dla ręcznej korekty.

    Zwraca {nazwa_pola: wartość} ograniczone do pól zadeklarowanych w schemacie.
    """
    import json

    fields_list = ", ".join(
        f"{f.get('name')} ({f.get('type', 'string')})" for f in (schema.get("fields") or [])
    ) or "—"
    system = (
        "Wyciągasz wartości pól nagłówkowych z dokumentu o ZNANYM typie. Zwróć wyłącznie "
        "JSON zgodny ze schematem. Podawaj wartości tylko dla wymienionych pól; pomiń "
        "pole, którego nie ma w dokumencie. Daty zwracaj w formacie YYYY-MM-DD."
    )
    user = (
        f"TYP DOKUMENTU: {schema.get('name', schema.get('slug'))}\n"
        f"POLA DO WYCIĄGNIĘCIA: {fields_list}\n"
        f"NAZWA PLIKU: {filename}\n\nDOKUMENT (początek):\n{text}"
    )
    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 600,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": _extract_response_format(schema),
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    out = _canonical_fields(parsed.get("fields") or [], schema)
    return _normalize_fields(out, schema)  # daty → YYYY-MM-DD


async def run_extraction(file_id: int, schemas: list[dict], filename: str = "") -> None:
    """Sklasyfikuj i wyciągnij pola dla pliku, ustaw READY, wznów kolejkę.

    Opcja B (#7B-2): plik wchodzi tu ze statusem „Przetwarzanie" (ustawionym przez
    handler READY) i DOPIERO TU przechodzi na „Przetworzono" — po zakończeniu
    klasyfikacji. Parsowanie się udało niezależnie od wyniku klasyfikacji, więc
    READY ustawiamy zawsze (klasyfikacja jest best-effort).

    Zakłada, że flaga extraction_started() jest już podniesiona przez wołającego.
    """
    import asyncio
    from app.database import SessionLocal
    from app.models import File as FileModel, DocumentStatus
    from app.qdrant_client import get_text_by_file_id
    from app.dispatcher import try_dispatch_next, mark_processing_finished

    db = SessionLocal()
    try:
        # Ręcznie zweryfikowany typ — nie nadpisuj auto-klasyfikacją (tylko sfinalizuj READY)
        vrow = db.query(FileModel).filter(FileModel.id == file_id).first()
        already_verified = bool(
            vrow and isinstance(vrow.metadata_, dict) and vrow.metadata_.get("doc_type_verified")
        )

        # 1) Klasyfikacja (best-effort), o ile typ nie został zatwierdzony ręcznie
        result = None
        if already_verified:
            logger.info(f"[EXTRACT] Plik {file_id}: typ zweryfikowany ręcznie — pomijam auto-klasyfikację")
        else:
            try:
                text = await asyncio.to_thread(get_text_by_file_id, file_id)
                if text:
                    result = await _classify(schemas, text, filename)
                else:
                    logger.info(f"[EXTRACT] Plik {file_id}: brak tekstu w Qdrancie — pomijam klasyfikację")
            except Exception as e:
                logger.warning(f"[EXTRACT] Plik {file_id}: klasyfikacja nieudana: {e}")

        # 2) Finalizacja: zapisz wynik (jeśli jest) i ustaw „Przetworzono".
        f = db.query(FileModel).filter(FileModel.id == file_id).first()
        if f:
            if result:
                meta = dict(f.metadata_ or {})
                meta["doc_type"] = result["doc_type"]
                meta["doc_fields"] = result["doc_fields"]
                f.metadata_ = meta
                logger.info(
                    f"[EXTRACT] Plik {file_id}: doc_type={result['doc_type']} "
                    f"pól={len(result['doc_fields'])}"
                )
                # Typ dokumentu trafia też do chunków w Qdrancie (best-effort)
                from app.qdrant_client import set_doc_type
                await asyncio.to_thread(set_doc_type, file_id, result["doc_type"])
            f.status = DocumentStatus.READY
            mark_processing_finished(f)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"[EXTRACT] Plik {file_id}: finalizacja nieudana: {e}")
        # Awaryjnie: nie zostawiaj pliku w „Przetwarzanie" — spróbuj ustawić READY.
        try:
            f = db.query(FileModel).filter(FileModel.id == file_id).first()
            if f and f.status != DocumentStatus.READY:
                f.status = DocumentStatus.READY
                mark_processing_finished(f)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        extraction_finished()
        try:
            await try_dispatch_next(db)  # wznów kolejkę wstrzymaną na czas ekstrakcji
        except Exception as e:
            logger.warning(f"[EXTRACT] Wznowienie kolejki po ekstrakcji nieudane: {e}")
        finally:
            db.close()
