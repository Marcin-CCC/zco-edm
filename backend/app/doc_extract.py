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

import httpx

from app.config import settings
from app.activity import extraction_finished

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


def _build_messages(schemas: list[dict], text: str) -> list[dict]:
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
        "Jesteś klasyfikatorem dokumentów urzędowych. Dostajesz katalog typów "
        "(z kryteriami i polami) oraz początek dokumentu. Wybierz NAJLEPIEJ pasujący "
        "typ (jego slug). Jeśli żaden nie pasuje, użyj doc_type='inny'. Następnie "
        "wyciągnij z dokumentu wartości pól WYŁĄCZNIE dla wybranego typu (nazwy pól "
        "dokładnie jak w katalogu). Jeśli pola nie ma w dokumencie — pomiń je. "
        "Zwróć wyłącznie JSON zgodny ze schematem."
    )
    user = f"{catalog}\n\nDOKUMENT (początek):\n{text}"
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


async def _classify(schemas: list[dict], text: str) -> dict | None:
    """Jedno wywołanie vLLM. Zwraca {'doc_type', 'doc_fields'} albo None przy błędzie."""
    import json

    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 600,
        "messages": _build_messages(schemas, text),
        "response_format": _response_format(schemas),
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    doc_type = (parsed.get("doc_type") or "").strip()
    # Zostaw tylko pola zadeklarowane w wybranym typie (odsiej szum modelu)
    allowed = set()
    for s in schemas:
        if s["slug"] == doc_type:
            allowed = {f.get("name") for f in (s.get("fields") or [])}
            break
    doc_fields = {}
    for item in parsed.get("fields") or []:
        name, value = item.get("name"), item.get("value")
        if name and value and (not allowed or name in allowed):
            doc_fields[name] = value
    return {"doc_type": doc_type, "doc_fields": doc_fields}


async def run_extraction(file_id: int, schemas: list[dict]) -> None:
    """Sklasyfikuj i wyciągnij pola dla pliku, zapisz w metadata_, wznów kolejkę.

    Zakłada, że flaga extraction_started() jest już podniesiona przez wołającego.
    """
    import asyncio
    from app.database import SessionLocal
    from app.models import File as FileModel
    from app.qdrant_client import get_text_by_file_id
    from app.dispatcher import try_dispatch_next

    db = SessionLocal()
    try:
        text = await asyncio.to_thread(get_text_by_file_id, file_id)
        if not text:
            logger.info(f"[EXTRACT] Plik {file_id}: brak tekstu w Qdrancie — pomijam klasyfikację")
            return

        result = await _classify(schemas, text)
        if not result:
            return

        f = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not f:
            return
        meta = dict(f.metadata_ or {})
        meta["doc_type"] = result["doc_type"]
        meta["doc_fields"] = result["doc_fields"]
        f.metadata_ = meta
        db.commit()
        logger.info(
            f"[EXTRACT] Plik {file_id}: doc_type={result['doc_type']} "
            f"pól={len(result['doc_fields'])}"
        )
    except Exception as e:
        db.rollback()
        logger.warning(f"[EXTRACT] Plik {file_id}: klasyfikacja nieudana: {e}")
    finally:
        extraction_finished()
        try:
            await try_dispatch_next(db)  # wznów kolejkę wstrzymaną na czas ekstrakcji
        except Exception as e:
            logger.warning(f"[EXTRACT] Wznowienie kolejki po ekstrakcji nieudane: {e}")
        finally:
            db.close()
