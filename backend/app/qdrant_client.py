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
