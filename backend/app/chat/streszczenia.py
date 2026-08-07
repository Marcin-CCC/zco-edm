"""Wskazywanie dokumentów po streszczeniu, gdy zwykłe fragmenty nie wystarczają.

Dlaczego to istnieje: pracownik pyta potocznie („jak rozliczyć delegację?"), a
dokument mówi urzędowo („podróż służbowa"). Zmierzone: żaden albo jeden fragment
z piętnastu przekracza próg 0,50 z węzła „Chunks Filter", więc kontekst zostaje
pusty i czat odpowiada, że nie znalazł informacji — mimo że dokument w bazie JEST.

Jak to działa:
 1. Backend powtarza to samo wyszukiwanie, które zrobi n8n, i patrzy, ile
    fragmentów przekracza próg. Jeśli co najmniej dwa — nie robimy nic, dzisiejsza
    ścieżka jest sprawna (zero ryzyka regresji dla pytań, które już działają).
 2. Jeśli mniej, pytamy kolekcji streszczeń, KTÓRE DOKUMENTY dotyczą tematu, i
    zawężamy wyszukiwanie n8n do nich (`metadata.file_id`) z wyłączonym progiem —
    tym samym mechanizmem, którym działa pytanie o wskazane pliki.

Czego to NIE robi: streszczenie nigdy nie wchodzi do kontekstu modelu. Odpowiedź
powstaje wyłącznie z oryginalnych fragmentów wskazanych dokumentów, a gdy ich
treść nie dotyczy pytania, model nadal odmawia — jego prompt tego wymaga.

Dlaczego trzy dokumenty, a nie jeden: wartości bezwzględne trafności streszczeń
nie rozdzielają trafień od nietrafień (zmierzone: pytanie o temat nieobecny w
bazie 0,484 wobec prawdziwego trafienia 0,431), rozdziela wyłącznie kolejność.
Dodatkowo dokumenty chodzą rodzinami (zarządzenie + regulamin + formularz) i
w bazie są duplikaty, więc pierwsze miejsce bywa najsłabszym z rodzeństwa.
"""

import logging

from app.config import settings
from app.qdrant_client import search_chunks, search_sections, search_summaries
from app.summaries import wektor

logger = logging.getLogger(__name__)

PROG_FRAGMENTU = 0.50    # ten sam próg, co węzeł „Chunks Filter" w n8n
MIN_FRAGMENTOW = 2       # poniżej tego kontekst jest pusty albo szczątkowy
MAX_DOKUMENTOW = 3       # ile dokumentów wskazuje streszczenie
LIMIT_FRAGMENTOW = 15    # topK węzła Qdrant w n8n
MAX_Z_SEKCJI = 3         # ile dokumentów dokładają streszczenia sekcyjne


def _pliki_z_sekcji(wektor_pytania, folder_ids, ile: int) -> list[int]:
    """Dokumenty wskazane przez streszczenia SEKCYJNE, bez powtórzeń.

    Dlaczego SUMA ZBIORÓW, a nie wspólny ranking (zmierzone 2026-08-07 na trzech
    pytaniach uruchamiających ratunek):

        dzisiaj (3 streszczenia całości)   1/3
        same sekcje                        2/3   — gubi krótkie dokumenty, bo te
                                                   sekcji nie mają wcale (53 pliki
                                                   ze 188 są dość długie)
        wspólny ranking po score           2/3   — streszczenia krótkich formularzy
                                                   wypychają właściwą sekcję poza
                                                   pierwszą trójkę (0,621 wobec 0,571)
        SUMA: 3 sekcje + 3 streszczenia    3/3

    Sekcje i streszczenia całości mierzą co innego i ich wartości score nie są
    porównywalne, więc każde źródło dostaje własne miejsca zamiast konkurować.
    """
    pliki: list[int] = []
    for s in search_sections(wektor_pytania, folder_ids=folder_ids, limit=ile * 3):
        fid = s.get("file_id")
        if fid is not None and fid not in pliki:
            pliki.append(int(fid))
        if len(pliki) >= ile:
            break
    return pliki


async def wskaz_dokumenty(pytanie: str, filtr_rbac: dict | None,
                          folder_ids: list[int] | None,
                          wektor_pytania: list[float] | None = None,
                          ) -> tuple[list[int], bool, str]:
    """Zwróć (file_ids do filtra, czy wyłączyć próg, opis diagnostyczny do logu).

    Dwa tryby:
     • ZAWĘŻENIE — fragmenty nie dają kontekstu (mniej niż dwa nad progiem). Wtedy
       zawężamy do dokumentów ze streszczeń i wyłączamy próg, bo wewnątrz jednego
       dokumentu trafności są z natury niższe.
     • UZUPEŁNIENIE — fragmenty są, ale streszczenia wskazują dokument, którego wśród
       nich NIE MA (zmierzone: „czy dostanę zwrot za paliwo w delegacji?" — 15/15
       fragmentów nad progiem, same rubryki formularza, a właściwy wniosek o użycie
       samochodu prywatnego w ogóle nie wchodzi do kontekstu). Dokładamy ten dokument
       do zbioru, ZOSTAWIAJĄC próg. Zbiór zawiera wszystkie dokumenty, które i tak
       przekroczyły próg, więc żaden dzisiejszy fragment nie może wypaść — filtr
       odcina wyłącznie to, co i tak było poniżej progu.

    Pusta lista = nie ingerujemy w dzisiejszą ścieżkę. Best-effort: każdy błąd
    (Qdrant, model osadzeń) kończy się pustą listą, czyli zachowaniem sprzed zmiany.
    """
    if wektor_pytania is not None:
        w = wektor_pytania          # policzone raz przez routera, dzielone z doborem
    else:
        try:
            w = await wektor(pytanie)
        except Exception as e:
            logger.warning(f"[STRESZCZENIE-ROUTE] Osadzenie pytania nieudane: {e}")
            return [], False, "brak osadzenia"

    fragmenty = search_chunks(w, filtr_rbac, limit=LIMIT_FRAGMENTOW)
    nad_progiem = [(s, fid) for s, fid in fragmenty if s >= PROG_FRAGMENTU]
    dokumenty_nad_progiem = [fid for _, fid in nad_progiem if fid is not None]

    wskazania = search_summaries(w, folder_ids=folder_ids, limit=MAX_DOKUMENTOW)
    skrot = [(round(s, 3), f) for s, f in wskazania]
    if not wskazania:
        return [], False, f"fragmentów nad progiem {len(nad_progiem)}, streszczenia bez wskazań"

    if len(nad_progiem) < MIN_FRAGMENTOW:
        ids = [fid for _, fid in wskazania]
        z_sekcji: list[int] = []
        if settings.SEKCJE_W_WYSZUKIWANIU:
            z_sekcji = [f for f in _pliki_z_sekcji(w, folder_ids, MAX_Z_SEKCJI)
                        if f not in ids]
            ids = z_sekcji + ids
        for fid in dokumenty_nad_progiem:
            if fid not in ids:
                ids.append(fid)
        return ids, True, (f"fragmentów nad progiem {len(nad_progiem)} → zawężam do {ids} "
                           f"(streszczenia: {skrot}"
                           f"{f', sekcje: {z_sekcji}' if z_sekcji else ''})")

    # Fragmenty są — dokładamy najwyżej dwa wskazane dokumenty, których wśród nich brak
    # (dwa, bo dokumenty chodzą parami docx/pdf i w bazie zdarzają się duplikaty).
    brakujace = [fid for _, fid in wskazania if fid not in dokumenty_nad_progiem][:2]
    if not brakujace:
        return [], False, f"fragmentów nad progiem {len(nad_progiem)} — bez zmian"

    ids = list(dict.fromkeys(dokumenty_nad_progiem + brakujace))
    return ids, False, (f"fragmentów nad progiem {len(nad_progiem)} → uzupełniam o {brakujace} "
                        f"(streszczenia: {skrot})")
