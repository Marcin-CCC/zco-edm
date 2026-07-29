"""Streszczenia dokumentów — magnes wyszukiwania dla pytań zadanych potocznie.

Problem: pracownik pyta „jak rozliczyć delegację?", a dokument mówi wyłącznie
o „podróży służbowej". Wektory tych sformułowań leżą na tyle daleko, że żaden
fragment nie przekracza progu i czat odpowiada, że nie wie. Pomiar (10 pytań
kontrolnych): „jak rozliczyć delegację?" 0,530 przy 1/10 fragmentów nad progiem,
„ile wynosi dieta za delegację?" 0,475 przy 0/10 — czyli pusta odpowiedź.

Rozwiązanie: dla każdego dokumentu trzymamy JEDEN dodatkowy punkt w osobnej
kolekcji (zob. qdrant_client.upsert_summary) — kilkuzdaniowy opis, w którym model
obowiązkowo wypisuje potoczne zamienniki i pytania w języku pracownika.

KLUCZOWE ograniczenie: streszczenie służy WYŁĄCZNIE do wskazania dokumentu.
Nigdy nie trafia do kontekstu modelu odpowiadającego — odpowiedź powstaje z
oryginalnych fragmentów wskazanego pliku. Dzięki temu streszczenie nie może
wprowadzić do odpowiedzi treści, której nie ma w dokumencie.

Wartości bezwzględne score streszczeń nie rozdzielają trafień od nietrafień
(pomiar: pytanie o nieistniejący temat dostało 0,484, a prawdziwe trafienie
w delegację 0,431), więc decyduje wyłącznie KOLEJNOŚĆ, a o odpowiedzi albo
odmowie i tak rozstrzygają fragmenty dokumentu.
"""

import asyncio
import logging

import httpx

from app.config import settings
from app.qdrant_client import ensure_summary_collection, get_text_by_file_id, upsert_summary

logger = logging.getLogger(__name__)

_kolekcja_gotowa = False       # kolekcję zakładamy raz, przy pierwszym streszczeniu
MODEL_WEKTOROW = "bge-m3:latest"
BUDZET_ZNAKOW = 12000          # ile tekstu dokumentu podajemy modelowi
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

SYSTEM = (
    "Tworzysz krótki opis dokumentu do wewnętrznej wyszukiwarki szpitala. Opis czyta "
    "MASZYNA dopasowująca pytania pracowników do dokumentów, nie człowiek.\n\n"
    "Zwróć dokładnie trzy części, każda od nowej linii:\n\n"
    "1. OPIS: 4-6 zdań o tym, czego dokument dotyczy i jakie sprawy załatwia. Wymień "
    "nazwy własne: numer dokumentu, datę, jednostki organizacyjne, osoby, nazwy formularzy.\n"
    "2. Linijka zaczynająca się od 'Inne określenia:' — wypisz po przecinku 5-10 słów i "
    "zwrotów POTOCZNYCH, którymi pracownik nazwie tę sprawę w pytaniu, nawet jeśli dokument "
    "używa innych słów. Przykłady zamienników: delegacja / podróż służbowa / wyjazd, "
    "L4 / zwolnienie lekarskie / chorobowe, wypowiedzenie / rozwiązanie umowy, "
    "socjal / ZFŚS / fundusz socjalny. Ta linijka jest OBOWIĄZKOWA.\n"
    "3. Linijka zaczynająca się od 'Pytania:' — 3-5 pytań, na które ten dokument "
    "odpowiada, sformułowanych tak, jak zapytałby pracownik.\n\n"
    "Zasady twarde:\n"
    "- Opieraj się WYŁĄCZNIE na treści dokumentu. Nie zgaduj i nie dopisuj rzeczy, "
    "których w nim nie ma.\n"
    "- Nazwiska, numery i daty przepisz DOSŁOWNIE z dokumentu, znak w znak. Jeśli nie "
    "jesteś pewien pisowni, pomiń je.\n"
    "- Żadnych nagłówków, komentarzy ani wstępów — zwróć sam opis."
)


def probka_tekstu(file_id: int, budzet: int = BUDZET_ZNAKOW) -> str:
    """Tekst dokumentu przycięty do budżetu — dla długich plików próbka z całości.

    Sam początek wystarcza w dokumencie dwustronicowym, ale w regulaminie na
    kilkadziesiąt stron pominąłby wszystko poza spisem treści. Bierzemy więc
    połowę budżetu z początku (tam są nazwy własne i tytuł), a resztę równomiernie
    z dalszej części dokumentu.
    """
    pelny = get_text_by_file_id(file_id, max_chars=400_000)
    if len(pelny) <= budzet:
        return pelny

    poczatek = pelny[: budzet // 2]
    reszta = pelny[budzet // 2:]
    ile_probek = 6
    dlugosc = (budzet - budzet // 2) // ile_probek
    krok = len(reszta) // ile_probek
    probki = [reszta[i * krok: i * krok + dlugosc] for i in range(ile_probek)]
    return poczatek + "\n[…]\n" + "\n[…]\n".join(probki)


async def opis_dokumentu(filename: str, tekst: str) -> str:
    """Wygeneruj opis przez vLLM. Rzuca wyjątek przy błędzie HTTP."""
    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0.2,
        "max_tokens": 600,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"NAZWA PLIKU: {filename}\n\nDOKUMENT:\n{tekst}"},
        ],
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


async def wektor(tekst: str) -> list[float]:
    """Osadzenie tekstu tym samym modelem, którym liczone są fragmenty (bge-m3)."""
    url = f"{settings.OLLAMA_API_URL.rstrip('/')}/api/embeddings"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json={"model": MODEL_WEKTOROW, "prompt": tekst})
    resp.raise_for_status()
    return resp.json()["embedding"]


async def odswiez_streszczenie(file_id: int, filename: str, folder_id: int | None) -> str | None:
    """Zbuduj i zapisz streszczenie jednego dokumentu. Best-effort — zwraca opis albo None.

    Nie może przerwać niczego, co ją woła: brak streszczenia oznacza tylko, że
    dokument nie zyska dodatkowej ścieżki wyszukiwania.
    """
    global _kolekcja_gotowa
    try:
        if not _kolekcja_gotowa:
            _kolekcja_gotowa = await asyncio.to_thread(ensure_summary_collection)
        tekst = await asyncio.to_thread(probka_tekstu, file_id)
        if not tekst:
            logger.info(f"[STRESZCZENIE] Plik {file_id}: brak tekstu w Qdrancie — pomijam")
            return None
        opis = await opis_dokumentu(filename, tekst)
        if not opis:
            return None
        w = await wektor(opis)
        payload = {
            "opis": opis,
            "file_id": int(file_id),
            "folder_id": folder_id,
            "filename": filename,
        }
        zapisano = await asyncio.to_thread(upsert_summary, file_id, w, payload)
        if zapisano:
            logger.info(f"[STRESZCZENIE] Plik {file_id}: zapisano ({len(opis)} zn.)")
            return opis
        return None
    except Exception as e:
        logger.warning(f"[STRESZCZENIE] Plik {file_id} nieudane: {e}")
        return None
