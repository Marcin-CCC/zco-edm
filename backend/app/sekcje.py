"""Streszczenia sekcyjne — opis KAŻDEJ części długiego dokumentu z osobna.

Po co: jedno streszczenie nie unosi wielotematycznego regulaminu. „Regulamin Pracy"
ma 106 tys. znaków i jeden opis, w którym nie mieszczą się naraz zwolnienia lekarskie,
urlop na żądanie, praca zdalna i czas pracy. Pytanie zadane potocznie trafia wtedy
w dokument przypadkowy albo w żaden. Zmierzone na bazie ZCO (2026-08-07): 67 dokumentów
dłuższych niż 12 tys. znaków mieści 3,12 mln z 3,48 mln znaków całej bazy — czyli
prawie cała treść leży w plikach, dla których jeden opis jest za mało.

Podział na sekcje: kolejne bloki do `BUDZET_ZNAKOW`, NIGDY nie dzielące strony.
Strona jest najmniejszą jednostką, którą umiemy zaadresować w wyszukiwaniu
(`metadata.page`), więc sekcja kończąca się w połowie strony byłaby nieadresowalna.

Sekcja zapisuje `strona_od`/`strona_do`, żeby wskazanie mogło zawęzić wyszukiwanie
do FRAGMENTU dokumentu, a nie do całego pliku — na tym polega przewaga nad
streszczeniem całości.

CZEGO TEN MODUŁ NIE ROBI: nie jest podłączony do wyszukiwania. Sekcje lądują
w osobnej kolekcji (`<kolekcja>_sekcje`), której dziś nic nie czyta. To celowe —
dołożenie ~300 celów do warstwy, o której wiemy, że nie rozdziela trafień od
nietrafień wartością score (zmierzone: błędne streszczenie 0,494 wobec właściwego
0,454), może pogorszyć wyniki. Decyzja o podłączeniu zapada PO pomiarze
(app/retrieval_bench.py), za przełącznikiem.

Nie generujemy sekcji w trakcie parsowania: dokument na 227 stron to ok. 42 wywołania
modelu, co wydłużyłoby przetwarzanie o kilkanaście–kilkadziesiąt minut i odebrało GPU
czatowi. Sekcje powstają wsadowo (app/sekcje_backfill.py).
"""

import asyncio
import logging

import httpx

from app.config import settings
from app.qdrant_client import (
    delete_sections,
    ensure_section_collection,
    get_chunks_by_file_id,
    upsert_section,
)
from app.summaries import wektor

logger = logging.getLogger(__name__)

BUDZET_ZNAKOW = 12000          # tyle samo, co budżet streszczenia dokumentu
MIN_ZNAKOW_SEKCJI = 500        # krótsza „sekcja" to resztka, nie temat
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

SYSTEM = (
    "Tworzysz krótki opis JEDNEJ CZĘŚCI dokumentu do wewnętrznej wyszukiwarki szpitala. "
    "Opis czyta MASZYNA dopasowująca pytania pracowników do właściwego fragmentu, nie człowiek.\n\n"
    "Zwróć dokładnie trzy części, każda od nowej linii:\n\n"
    "1. OPIS: 3-5 zdań o tym, jakie sprawy załatwia TA CZĘŚĆ dokumentu. Pisz wyłącznie "
    "o tym, co jest w podanym tekście — nie streszczaj całego dokumentu.\n"
    "2. Linijka zaczynająca się od 'Inne określenia:' — po przecinku 5-10 słów i zwrotów "
    "POTOCZNYCH, którymi pracownik nazwie te sprawy w pytaniu. Przykłady zamienników: "
    "delegacja / podróż służbowa, L4 / zwolnienie lekarskie / chorobowe, "
    "socjal / ZFŚS / fundusz socjalny. Ta linijka jest OBOWIĄZKOWA.\n"
    "3. Linijka zaczynająca się od 'Pytania:' — 3-5 pytań, na które odpowiada TA CZĘŚĆ, "
    "sformułowanych tak, jak zapytałby pracownik.\n\n"
    "Zasady twarde:\n"
    "- Opieraj się WYŁĄCZNIE na podanym tekście. Nie zgaduj, czego dotyczą pozostałe części.\n"
    "- Nazwiska, numery i daty przepisz DOSŁOWNIE, znak w znak. Jeśli nie jesteś pewien "
    "pisowni, pomiń je.\n"
    "- Żadnych nagłówków, komentarzy ani wstępów — zwróć sam opis."
)


def podziel_na_sekcje(file_id: int, budzet: int = BUDZET_ZNAKOW) -> list[dict]:
    """Podziel dokument na bloki [{strona_od, strona_do, tekst}].

    Blok rośnie do wyczerpania budżetu, ale zamyka się zawsze na granicy strony.
    Strona dłuższa niż budżet trafia do bloku sama — nie tniemy jej, bo i tak nie
    umiemy zaadresować jej połowy.
    """
    fragmenty = get_chunks_by_file_id(file_id)
    if not fragmenty:
        return []

    # Sklej treść w obrębie strony (fragmenty są już posortowane)
    strony: list[tuple[int, str]] = []
    for strona, _wiersz, tresc in fragmenty:
        if not (tresc or "").strip():
            continue
        if strony and strony[-1][0] == strona:
            strony[-1] = (strona, strony[-1][1] + "\n" + tresc)
        else:
            strony.append((strona, tresc))
    if not strony:
        return []

    sekcje: list[dict] = []
    biezaca: list[tuple[int, str]] = []
    dlugosc = 0
    for strona, tresc in strony:
        if biezaca and dlugosc + len(tresc) > budzet:
            sekcje.append(_zloz(biezaca))
            biezaca, dlugosc = [], 0
        biezaca.append((strona, tresc))
        dlugosc += len(tresc)
    if biezaca:
        sekcje.append(_zloz(biezaca))

    # Ogon krótszy niż minimum doklejamy do poprzedniej sekcji zamiast opisywać osobno
    if len(sekcje) > 1 and len(sekcje[-1]["tekst"]) < MIN_ZNAKOW_SEKCJI:
        ogon = sekcje.pop()
        sekcje[-1]["tekst"] += "\n" + ogon["tekst"]
        sekcje[-1]["strona_do"] = ogon["strona_do"]
    return sekcje


def _zloz(strony: list[tuple[int, str]]) -> dict:
    return {
        "strona_od": strony[0][0],
        "strona_do": strony[-1][0],
        "tekst": "\n".join(t for _, t in strony),
    }


async def opis_sekcji(filename: str, sekcja: dict) -> str:
    """Opis jednej sekcji przez vLLM. Rzuca wyjątek przy błędzie HTTP."""
    naglowek = (f"NAZWA PLIKU: {filename}\n"
                f"CZĘŚĆ DOKUMENTU: strony {sekcja['strona_od']}-{sekcja['strona_do']}\n\n"
                f"TREŚĆ:\n{sekcja['tekst']}")
    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0.2,
        "max_tokens": 500,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": naglowek},
        ],
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


async def odswiez_sekcje(file_id: int, filename: str, folder_id: int | None) -> int:
    """Zbuduj i zapisz sekcje jednego dokumentu. Zwraca liczbę zapisanych.

    Best-effort: pojedyncza nieudana sekcja nie przerywa pozostałych, a awaria
    całości zwraca 0. Stare sekcje kasujemy PRZED zapisem nowych, bo przy zmianie
    podziału zostałyby sieroty.
    """
    from app.summaries import ma_linie_zamiennikow

    try:
        if not ensure_section_collection():
            return 0
        sekcje = await asyncio.to_thread(podziel_na_sekcje, file_id)
        if len(sekcje) < 2:
            # Dokument mieści się w jednym bloku — streszczenie całości mu wystarcza
            return 0
        await asyncio.to_thread(delete_sections, file_id)
    except Exception as e:
        logger.warning(f"[SEKCJE] Plik {file_id}: przygotowanie nieudane: {e}")
        return 0

    zapisane = 0
    for numer, sekcja in enumerate(sekcje):
        try:
            opis = await opis_sekcji(filename, sekcja)
            if opis and not ma_linie_zamiennikow(opis):
                logger.info(f"[SEKCJE] Plik {file_id} sekcja {numer}: brak zamienników")
            if not opis:
                continue
            w = await wektor(opis)
            payload = {
                "opis": opis,
                "file_id": int(file_id),
                "folder_id": folder_id,
                "filename": filename,
                "strona_od": sekcja["strona_od"],
                "strona_do": sekcja["strona_do"],
            }
            if await asyncio.to_thread(upsert_section, file_id, numer, w, payload):
                zapisane += 1
        except Exception as e:
            logger.warning(f"[SEKCJE] Plik {file_id} sekcja {numer} nieudana: {e}")

    logger.info(f"[SEKCJE] Plik {file_id}: zapisano {zapisane}/{len(sekcje)} sekcji")
    return zapisane
