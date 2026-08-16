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


def set_doc_type(file_id: int, doc_type: str | None) -> dict:
    """Dopisz `doc_type` do payloadów wszystkich chunków danego pliku.

    Klucz jest TOP-LEVEL (obok `content` i `metadata`), a nie w środku `metadata` —
    dzięki temu operacja tylko dokłada pole i nie może nadpisać istniejących metadanych
    (w tym `metadata.folder_id`, na którym opiera się filtr RBAC czatu).

    Dzięki temu typ dokumentu jest dostępny przy wyszukiwaniu wektorowym (filtrowanie
    lub premiowanie po typie) — dziś tylko go zapisujemy.

    Best-effort: awaria Qdranta nie może przerwać klasyfikacji. Zwraca diagnostykę.
    """
    if not doc_type:
        return {"ok": False, "reason": "brak doc_type"}

    base = settings.QDRANT_URL.rstrip("/")
    collection = settings.QDRANT_COLLECTION
    url = f"{base}/collections/{collection}/points/payload?wait=true"
    body = {
        "payload": {"doc_type": doc_type},
        "filter": {"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]},
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis doc_type dla pliku {file_id} nieudany: {e}")
        return {"ok": False, "error": str(e)}

    if resp.status_code == 200:
        logger.info(f"[QDRANT] Plik {file_id}: doc_type='{doc_type}' zapisany w chunkach")
        return {"ok": True}
    logger.warning(
        f"[QDRANT] Zapis doc_type pliku {file_id}: HTTP {resp.status_code}: {resp.text[:200]}"
    )
    return {"ok": False, "status": resp.status_code}


def set_folder_id(file_id: int, folder_id: int | None) -> dict:
    """Zaktualizuj `metadata.folder_id` we wszystkich chunkach pliku.

    KRYTYCZNE dla kontroli dostępu: czat filtruje wyszukiwanie po
    `metadata.folder_id` (filtr RBAC roli). Po przeniesieniu pliku do innego
    folderu chunki muszą nieść nowy folder, inaczej dokument nadal „należałby"
    do starego folderu w wyszukiwaniu treści.

    Używa parametru `key` (Qdrant ≥1.8) — ustawia pole WEWNĄTRZ `metadata`,
    nie nadpisując pozostałych metadanych (file_id, filename, page…).
    """
    base = settings.QDRANT_URL.rstrip("/")
    collection = settings.QDRANT_COLLECTION
    url = f"{base}/collections/{collection}/points/payload?wait=true"
    body = {
        "payload": {"folder_id": folder_id},
        "key": "metadata",
        "filter": {"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]},
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis folder_id dla pliku {file_id} nieudany: {e}")
        return {"ok": False, "error": str(e)}

    if resp.status_code == 200:
        logger.info(f"[QDRANT] Plik {file_id}: folder_id={folder_id} zapisany w chunkach")
        return {"ok": True}
    logger.warning(
        f"[QDRANT] Zapis folder_id pliku {file_id}: HTTP {resp.status_code}: {resp.text[:200]}"
    )
    return {"ok": False, "status": resp.status_code}


def get_chunks_by_file_id(file_id: int) -> list[tuple[int, int, str]]:
    """Fragmenty JEDNEGO dokumentu jako [(strona, wiersz, treść)], posortowane.

    Numer strony jest potrzebny streszczeniom sekcyjnym (app/sekcje.py): sekcja musi
    wiedzieć, których stron dotyczy, żeby dało się do nich zawęzić wyszukiwanie.
    """
    base = settings.QDRANT_URL.rstrip("/")
    collection = settings.QDRANT_COLLECTION
    url = f"{base}/collections/{collection}/points/scroll"
    body = {
        "limit": 500,
        "with_payload": True,
        "with_vector": False,
        "filter": {"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]},
    }
    parts: list[tuple[int, int, str]] = []
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
                    page = meta.get("page") or 0
                    line_from = (((meta.get("loc") or {}).get("lines") or {}).get("from")) or 0
                    parts.append((int(page), int(line_from), payload.get("content") or ""))
                offset = result.get("next_page_offset")
                if not offset:
                    break
    except Exception as e:
        logger.warning(f"[QDRANT] Odczyt fragmentów pliku {file_id} nieudany: {e}")
        return []

    parts.sort(key=lambda p: (p[0], p[1]))
    return parts


def get_text_by_file_id(file_id: int, max_chars: int = 6000) -> str:
    """Odtwórz tekst JEDNEGO dokumentu z chunków w Qdrancie (dla klasyfikacji #7B-2).

    Zwraca początek dokumentu (do `max_chars`) — do klasyfikacji typu i pól
    nagłówkowych wystarcza nagłówek/pierwsze strony. Pusty string, gdy brak chunków.
    """
    parts = get_chunks_by_file_id(file_id)
    text = "\n".join(p[2] for p in parts if p[2]).strip()
    return text[:max_chars]


def search_chunks(
    wektor: list[float], filtr: dict | None = None, limit: int = 15
) -> list[tuple[float, int | None]]:
    """Zwróć [(score, file_id)] fragmentów — tak samo jak węzeł Qdrant w n8n.

    Backend używa tego do OCENY, czy zwykłe wyszukiwanie ma czym odpowiedzieć
    (zob. app/chat/streszczenia.py). Kontekst dla modelu nadal składa n8n.
    """
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{settings.QDRANT_COLLECTION}/points/search"
    body: dict = {"vector": wektor, "limit": limit, "with_payload": True}
    if filtr:
        body["filter"] = filtr
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        wyniki = []
        for p in resp.json()["result"]:
            meta = (p.get("payload") or {}).get("metadata") or {}
            fid = meta.get("file_id")
            wyniki.append((float(p["score"]), int(fid) if fid is not None else None))
        return wyniki
    except Exception as e:
        logger.warning(f"[QDRANT] Wyszukiwanie fragmentów nieudane: {e}")
        return []


def search_chunks_full(
    wektor: list[float], filtr: dict | None = None, limit: int = 15
) -> list[dict]:
    """To samo wyszukiwanie, co `search_chunks`, ale z TREŚCIĄ i nazwą pliku.

    Potrzebne doborowi z dokumentu-zwycięzcy (app/chat/dobor.py): żeby ocenić,
    której części pytania kontekst NIE POKRYWA, trzeba zobaczyć teksty fragmentów,
    a nie same trafności. Osobna funkcja, bo `search_chunks` zwraca krotki i jest
    używana tam, gdzie treść jest zbędna.
    """
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{settings.QDRANT_COLLECTION}/points/search"
    body: dict = {"vector": wektor, "limit": limit, "with_payload": True}
    if filtr:
        body["filter"] = filtr
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        wyniki = []
        for p in resp.json()["result"]:
            payload = p.get("payload") or {}
            meta = payload.get("metadata") or {}
            fid = meta.get("file_id")
            wyniki.append({
                "score": float(p["score"]),
                "file_id": int(fid) if fid is not None else None,
                "filename": meta.get("filename"),
                "page": meta.get("page"),
                "content": payload.get("content") or "",
            })
        return wyniki
    except Exception as e:
        logger.warning(f"[QDRANT] Wyszukiwanie fragmentów (z treścią) nieudane: {e}")
        return []


def count_chunks_with_text(term: str) -> int | None:
    """Ile fragmentów zawiera dane słowo (indeks pełnotekstowy na `content`).

    Służy do oceny, czy słowo jest na tyle rzadkie, by zawężać po nim wyszukiwanie
    (nazwisko, numer, nazwa własna) — zob. app/chat/lexical.py. Zwraca None przy
    awarii: nie znamy rzadkości, więc wołający pomija takie słowo.
    """
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{settings.QDRANT_COLLECTION}/points/count"
    body = {"filter": {"must": [{"key": "content", "match": {"text": term}}]}, "exact": True}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        return int(resp.json()["result"]["count"])
    except Exception as e:
        logger.warning(f"[QDRANT] Zliczanie fragmentów dla {term!r} nieudane: {e}")
        return None


# ---------------------------------------------------------------------------
# Streszczenia dokumentów — OSOBNA kolekcja
#
# Streszczenie to „magnes wyszukiwania": zawiera potoczne określenia, którymi
# pracownik nazwie sprawę w pytaniu („delegacja" zamiast „podróż służbowa").
# Trzymamy je w osobnej kolekcji, a NIE obok fragmentów, z dwóch powodów:
#  1. istniejąca ścieżka RAG (n8n) nie może ich przypadkiem wciągnąć do kontekstu
#     modelu — odpowiedź ma powstawać wyłącznie z oryginalnych fragmentów;
#  2. zero ryzyka regresji: nic w dzisiejszym przepływie tej kolekcji nie widzi.
# Streszczenie służy TYLKO do wskazania dokumentu (zob. app/summaries.py).
# ---------------------------------------------------------------------------

def _kolekcja_streszczen() -> str:
    return f"{settings.QDRANT_COLLECTION}_streszczenia"


def ensure_summary_collection(rozmiar_wektora: int = 1024) -> bool:
    """Utwórz kolekcję streszczeń, jeśli jeszcze nie istnieje (idempotentne)."""
    base = settings.QDRANT_URL.rstrip("/")
    nazwa = _kolekcja_streszczen()
    try:
        with httpx.Client(timeout=15.0) as client:
            if client.get(f"{base}/collections/{nazwa}").status_code == 200:
                return True
            resp = client.put(
                f"{base}/collections/{nazwa}",
                json={"vectors": {"size": rozmiar_wektora, "distance": "Cosine"}},
            )
        resp.raise_for_status()
        logger.info(f"[QDRANT] Utworzono kolekcję streszczeń {nazwa}")
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Utworzenie kolekcji {nazwa} nieudane: {e}")
        return False


def ensure_text_index() -> bool:
    """Dopilnuj indeksu pełnotekstowego na polu `content` w kolekcji fragmentów.

    Bez tego indeksu dopasowanie po słowie (`match.text`) zwraca ZERO dla każdego
    słowa — także dla tych, które w dokumentach są. Cicho psuje to dwie rzeczy:
    zawężanie leksykalne po nazwach własnych (app/chat/lexical.py) oraz wykrywanie
    skrótów spoza dokumentów (app/chat/skroty.py), które wtedy ostrzegałoby o
    KAŻDYM skrócie.

    Zmierzone 2026-08-06 na nowej instancji: kolekcja założona ręcznie nie miała
    indeksu (kolekcję ZCO utworzył kiedyś n8n i indeks tam był), więc „ppk" dawało
    0 trafień przy 124 fragmentach w bazie. Parametry MUSZĄ być te same, co w ZCO —
    inaczej tokenizacja rozjedzie się między instancjami.
    """
    base = settings.QDRANT_URL.rstrip("/")
    nazwa = settings.QDRANT_COLLECTION
    parametry = {"type": "text", "tokenizer": "prefix",
                 "min_token_len": 3, "max_token_len": 20, "lowercase": True}
    try:
        with httpx.Client(timeout=15.0) as client:
            info = client.get(f"{base}/collections/{nazwa}")
            if info.status_code != 200:
                return False                      # kolekcji jeszcze nie ma — nie nasza rola
            schemat = (info.json().get("result") or {}).get("payload_schema") or {}
            if "content" in schemat:
                return True
            resp = client.put(f"{base}/collections/{nazwa}/index?wait=true",
                              json={"field_name": "content", "field_schema": parametry})
        resp.raise_for_status()
        logger.info(f"[QDRANT] Utworzono indeks pełnotekstowy `content` w {nazwa}")
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Indeks pełnotekstowy w {nazwa} nieudany: {e}")
        return False


def upsert_summary(file_id: int, wektor: list[float], payload: dict) -> bool:
    """Zapisz streszczenie dokumentu. Identyfikator punktu = file_id, więc
    ponowne wygenerowanie nadpisuje poprzednie i nie tworzy duplikatów."""
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points?wait=true"
    body = {"points": [{"id": int(file_id), "vector": wektor, "payload": payload}]}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.put(url, json=body)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis streszczenia pliku {file_id} nieudany: {e}")
        return False


def delete_summary(file_id: int) -> bool:
    """Usuń streszczenie pliku (wołane razem z usuwaniem jego fragmentów)."""
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points/delete?wait=true"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json={"points": [int(file_id)]})
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Usuwanie streszczenia pliku {file_id} nieudane: {e}")
        return False


def set_filename(file_id: int, filename: str) -> dict:
    """Zaktualizuj `metadata.filename` we wszystkich chunkach pliku.

    Nazwa z payloadu Qdranta jest tym, co użytkownik widzi pod odpowiedzią czatu.
    Bez tej aktualizacji dokument po zmianie nazwy pokazywałby się w źródłach pod
    starą — a wtedy nadawanie sensownych nazw nie dałoby nic akurat tam, gdzie
    najbardziej pomaga.

    Parametr `key` ustawia pole WEWNĄTRZ `metadata`, nie ruszając reszty
    (file_id, page, folder_id).
    """
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{settings.QDRANT_COLLECTION}/points/payload?wait=true"
    body = {
        "payload": {"filename": filename},
        "key": "metadata",
        "filter": {"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]},
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        return {"ok": True}
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis nazwy pliku {file_id} nieudany: {e}")
        return {"ok": False, "error": str(e)}


def set_summary_filename(file_id: int, filename: str) -> bool:
    """To samo dla streszczenia dokumentu — wskazywanie dokumentów pokazuje nazwę."""
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points/payload?wait=true"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json={"payload": {"filename": filename},
                                          "points": [int(file_id)]})
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis nazwy streszczenia pliku {file_id} nieudany: {e}")
        return False


def set_summary_folder_id(file_id: int, folder_id: int | None) -> bool:
    """Zaktualizuj folder w streszczeniu po przeniesieniu pliku (filtr RBAC)."""
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points/payload?wait=true"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json={"payload": {"folder_id": folder_id},
                                          "points": [int(file_id)]})
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis folderu streszczenia pliku {file_id} nieudany: {e}")
        return False


def search_summaries(
    wektor: list[float], folder_ids: list[int] | None = None, limit: int = 5
) -> list[tuple[float, int]]:
    """Zwróć [(score, file_id)] najbliższych streszczeń, z filtrem RBAC po folderach.

    `folder_ids=None` oznacza brak ograniczenia (administrator); pusta lista —
    użytkownik bez dostępu do czegokolwiek, więc od razu pusty wynik.
    """
    if folder_ids is not None and not folder_ids:
        return []
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points/search"
    body: dict = {"vector": wektor, "limit": limit, "with_payload": True}
    if folder_ids is not None:
        body["filter"] = {"must": [{"key": "folder_id", "match": {"any": folder_ids}}]}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        return [(float(p["score"]), int(p["id"])) for p in resp.json()["result"]]
    except Exception as e:
        logger.warning(f"[QDRANT] Wyszukiwanie streszczeń nieudane: {e}")
        return []


def summary_ids() -> set[int]:
    """Identyfikatory plików, które mają już streszczenie (id punktu = file_id)."""
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points/scroll"
    ids: set[int] = set()
    try:
        with httpx.Client(timeout=30.0) as client:
            offset = None
            while True:
                body = {"limit": 500, "with_payload": False, "with_vector": False}
                if offset is not None:
                    body["offset"] = offset
                resp = client.post(url, json=body)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                ids.update(int(p["id"]) for p in result.get("points", []))
                offset = result.get("next_page_offset")
                if not offset:
                    break
    except Exception as e:
        logger.warning(f"[QDRANT] Odczyt listy streszczeń nieudany: {e}")
    return ids


def summary_payloads() -> dict[int, dict]:
    """{file_id: payload} wszystkich streszczeń — z treścią opisu.

    `summary_ids()` odpowiada tylko na pytanie „czy streszczenie istnieje", a to
    za mało, żeby znaleźć streszczenia NIEPEŁNE (bez linii „Inne określenia”).
    """
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_streszczen()}/points/scroll"
    wynik: dict[int, dict] = {}
    try:
        with httpx.Client(timeout=30.0) as client:
            offset = None
            while True:
                body = {"limit": 500, "with_payload": True, "with_vector": False}
                if offset is not None:
                    body["offset"] = offset
                resp = client.post(url, json=body)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                for p in result.get("points", []):
                    wynik[int(p["id"])] = p.get("payload") or {}
                offset = result.get("next_page_offset")
                if not offset:
                    break
    except Exception as e:
        logger.warning(f"[QDRANT] Odczyt treści streszczeń nieudany: {e}")
    return wynik


def count_summaries() -> int:
    """Ile dokumentów ma już streszczenie."""
    base = settings.QDRANT_URL.rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/collections/{_kolekcja_streszczen()}")
        resp.raise_for_status()
        return int(resp.json()["result"].get("points_count") or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Streszczenia SEKCYJNE — trzecia kolekcja
#
# Jedno streszczenie nie unosi wielotematycznego regulaminu: „Regulamin Pracy" na
# 106 tys. znaków dostaje jeden opis, w którym nie mieści się ani L4, ani urlop na
# żądanie, ani praca zdalna. Sekcja to blok kolejnych stron, opisany osobno i ze
# świadomością, których stron dotyczy — dzięki temu wskazanie może zawęzić
# wyszukiwanie do FRAGMENTU dokumentu, a nie do całości.
#
# Osobna kolekcja z tego samego powodu, co przy streszczeniach dokumentów: dopóki
# nic jej nie czyta, nie może niczego zepsuć. Podłączenie do wyszukiwania jest
# osobną decyzją, podejmowaną po pomiarze (app/retrieval_bench.py).
# ---------------------------------------------------------------------------

MAX_SEKCJI_NA_PLIK = 1000     # ogranicza schemat identyfikatora punktu


def _kolekcja_sekcji() -> str:
    return f"{settings.QDRANT_COLLECTION}_sekcje"


def ensure_section_collection(rozmiar_wektora: int = 1024) -> bool:
    """Utwórz kolekcję sekcji, jeśli jeszcze nie istnieje (idempotentne)."""
    base = settings.QDRANT_URL.rstrip("/")
    nazwa = _kolekcja_sekcji()
    try:
        with httpx.Client(timeout=15.0) as client:
            if client.get(f"{base}/collections/{nazwa}").status_code == 200:
                return True
            resp = client.put(
                f"{base}/collections/{nazwa}",
                json={"vectors": {"size": rozmiar_wektora, "distance": "Cosine"}},
            )
        resp.raise_for_status()
        logger.info(f"[QDRANT] Utworzono kolekcję sekcji {nazwa}")
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Utworzenie kolekcji {nazwa} nieudane: {e}")
        return False


def upsert_section(file_id: int, numer: int, wektor: list[float], payload: dict) -> bool:
    """Zapisz jedną sekcję. Identyfikator = file_id * 1000 + numer, więc ponowne
    wygenerowanie nadpisuje poprzednie zamiast mnożyć punkty."""
    if not 0 <= numer < MAX_SEKCJI_NA_PLIK:
        logger.warning(f"[QDRANT] Sekcja {numer} pliku {file_id} poza zakresem — pomijam")
        return False
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_sekcji()}/points?wait=true"
    punkt = {"id": int(file_id) * MAX_SEKCJI_NA_PLIK + int(numer),
             "vector": wektor, "payload": payload}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.put(url, json={"points": [punkt]})
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Zapis sekcji {numer} pliku {file_id} nieudany: {e}")
        return False


def delete_sections(file_id: int) -> bool:
    """Usuń WSZYSTKIE sekcje pliku — filtrem po `file_id`, nie po identyfikatorach.

    Liczba sekcji zmienia się przy ponownym parsowaniu (inny podział na strony),
    więc kasowanie po wyliczonych identyfikatorach zostawiałoby sieroty.
    """
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_sekcji()}/points/delete?wait=true"
    body = {"filter": {"must": [{"key": "file_id", "match": {"value": int(file_id)}}]}}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[QDRANT] Usuwanie sekcji pliku {file_id} nieudane: {e}")
        return False


def search_sections(
    wektor: list[float], folder_ids: list[int] | None = None, limit: int = 5
) -> list[dict]:
    """[{score, file_id, filename, strona_od, strona_do}] najbliższych sekcji."""
    if folder_ids is not None and not folder_ids:
        return []
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_sekcji()}/points/search"
    body: dict = {"vector": wektor, "limit": limit, "with_payload": True}
    if folder_ids is not None:
        body["filter"] = {"must": [{"key": "folder_id", "match": {"any": folder_ids}}]}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
        resp.raise_for_status()
        wyniki = []
        for p in resp.json()["result"]:
            pay = p.get("payload") or {}
            wyniki.append({
                "score": float(p["score"]),
                "file_id": pay.get("file_id"),
                "filename": pay.get("filename"),
                "strona_od": pay.get("strona_od"),
                "strona_do": pay.get("strona_do"),
            })
        return wyniki
    except Exception as e:
        logger.warning(f"[QDRANT] Wyszukiwanie sekcji nieudane: {e}")
        return []


def section_file_ids() -> set[int]:
    """Pliki, które mają już wygenerowane sekcje (do wznawiania backfillu)."""
    base = settings.QDRANT_URL.rstrip("/")
    url = f"{base}/collections/{_kolekcja_sekcji()}/points/scroll"
    ids: set[int] = set()
    try:
        with httpx.Client(timeout=30.0) as client:
            offset = None
            while True:
                body = {"limit": 500, "with_payload": True, "with_vector": False}
                if offset is not None:
                    body["offset"] = offset
                resp = client.post(url, json=body)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                for p in result.get("points", []):
                    fid = (p.get("payload") or {}).get("file_id")
                    if fid is not None:
                        ids.add(int(fid))
                offset = result.get("next_page_offset")
                if not offset:
                    break
    except Exception as e:
        logger.warning(f"[QDRANT] Odczyt listy sekcji nieudany: {e}")
    return ids


def count_sections() -> int:
    """Ile sekcji jest zapisanych (diagnostyka backfillu)."""
    base = settings.QDRANT_URL.rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/collections/{_kolekcja_sekcji()}")
        resp.raise_for_status()
        return int(resp.json()["result"].get("points_count") or 0)
    except Exception:
        return 0


def count_points() -> int:
    """Liczba fragmentów w kolekcji (do skalowania progu rzadkości)."""
    base = settings.QDRANT_URL.rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/collections/{settings.QDRANT_COLLECTION}")
        resp.raise_for_status()
        return int(resp.json()["result"].get("points_count") or 0)
    except Exception as e:
        logger.warning(f"[QDRANT] Odczyt rozmiaru kolekcji nieudany: {e}")
        return 0
