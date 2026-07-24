"""
Minimalny klient Qdranta — na razie tylko usuwanie wektorów pliku.

Wektory zapisuje workflow n8n (Qdrant Vector Store) z payloadem zawierającym
`metadata.file_id` (liczba). Przy usuwaniu pliku backend kasuje jego wektory
filtrem po tym polu, żeby wygasłe/usunięte dokumenty nie odpowiadały już
w czacie.

Zasada: best-effort. Awaria Qdranta NIE może przerwać usuwania pliku —
funkcja loguje ostrzeżenie i zwraca słownik diagnostyczny.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def delete_vectors_by_file_id(file_id: int) -> dict:
    """Usuń z Qdranta wszystkie wektory danego pliku (filtr metadata.file_id).

    Zwraca: {"ok": bool, ...diagnostyka}. Nie rzuca wyjątków.
    """
    base = settings.QDRANT_URL.rstrip("/")
    collection = settings.QDRANT_COLLECTION
    # wait=true — Qdrant potwierdza zakończenie operacji (spójny odczyt po usunięciu)
    url = f"{base}/collections/{collection}/points/delete?wait=true"
    body = {
        "filter": {
            "must": [{"key": "metadata.file_id", "match": {"value": file_id}}]
        }
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=body)
    except Exception as e:
        logger.warning(f"[QDRANT] Usuwanie wektorów pliku {file_id} nieudane (Qdrant nieosiągalny): {e}")
        return {"ok": False, "error": str(e)}

    if resp.status_code == 200:
        logger.info(f"[QDRANT] Usunięto wektory pliku {file_id} z kolekcji {collection}")
        return {"ok": True, "status": 200}

    logger.warning(
        f"[QDRANT] Usuwanie wektorów pliku {file_id}: HTTP {resp.status_code}: {resp.text[:200]}"
    )
    return {"ok": False, "status": resp.status_code, "detail": resp.text[:200]}


def get_texts_by_folder(folder_id: int | None = None) -> dict[int, str]:
    """Odtwórz tekst dokumentów sklejając ich chunki z Qdranta.

    Workflow parsowania NIE zapisuje tekstu do Postgresa (kończy się PATCH-em
    statusu bez `ocr_result`), ale zapisuje chunki w Qdrancie z payloadem
    `content` oraz `metadata.{file_id, folder_id, page, loc}`. Ta funkcja czyta
    je z powrotem: filtruje po `metadata.folder_id` (jeśli podano), grupuje po
    `file_id` i skleja `content` w kolejności (page, wiersz), odtwarzając tekst
    dokumentu na potrzeby INDUKCJI schematów.

    Zwraca: {file_id: pełny_tekst}. Dane nie opuszczają LAN Sparka.
    """
    base = settings.QDRANT_URL.rstrip("/")
    collection = settings.QDRANT_COLLECTION
    url = f"{base}/collections/{collection}/points/scroll"

    body: dict = {"limit": 500, "with_payload": True, "with_vector": False}
    if folder_id is not None:
        body["filter"] = {
            "must": [{"key": "metadata.folder_id", "match": {"value": folder_id}}]
        }

    # file_id -> lista (page, line_from, content) do posortowania
    chunks: dict[int, list[tuple[int, int, str]]] = {}
    try:
        with httpx.Client(timeout=30.0) as client:
            offset = None
            while True:
                page_body = dict(body)
                if offset is not None:
                    page_body["offset"] = offset
                resp = client.post(url, json=page_body)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                for pt in result.get("points", []):
                    payload = pt.get("payload") or {}
                    meta = payload.get("metadata") or {}
                    fid = meta.get("file_id")
                    if fid is None:
                        continue
                    page = meta.get("page") or 0
                    line_from = (((meta.get("loc") or {}).get("lines") or {}).get("from")) or 0
                    content = payload.get("content") or ""
                    chunks.setdefault(int(fid), []).append((int(page), int(line_from), content))
                offset = result.get("next_page_offset")
                if not offset:
                    break
    except Exception as e:
        logger.warning(f"[QDRANT] Odczyt tekstów (folder={folder_id}) nieudany: {e}")
        return {}

    texts: dict[int, str] = {}
    for fid, parts in chunks.items():
        parts.sort(key=lambda p: (p[0], p[1]))
        texts[fid] = "\n".join(p[2] for p in parts if p[2]).strip()
    return texts
