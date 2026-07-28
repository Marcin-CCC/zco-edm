"""Warstwa leksykalna wyszukiwania: nazwiska i inne nazwy własne.

Wyszukiwanie semantyczne mierzy podobieństwo TEMATYCZNE, więc pytanie „kim jest
Jolanta Dynarska" nie przypomina wiersza tabeli, w którym nazwisko jest jednym
z czterdziestu tokenów obok innych nazwisk, dat i kresek. Zmierzone na naszej
bazie: właściwe fragmenty dostawały 0,28–0,40 i lądowały NIŻEJ niż przypadkowe,
a ten sam wiersz podany jako zapytanie osiągał 0,568. Obniżenie progu tego nie
naprawia — wpuszcza śmieci przy każdym innym pytaniu.

Rozwiązanie: dopasowanie po słowie (indeks pełnotekstowy Qdranta na polu
`content`, tokenizer `prefix` + lowercase) jako sposób ZAWĘŻENIA zakresu —
dokładnie tym samym kanałem, którym zawężamy do wskazanych dokumentów.

Zawężamy wyłącznie po słowach RZADKICH. Słowo pospolite („pracy" — 658 z 1189
fragmentów) nie niesie informacji o zakresie, a zawężenie po nim zepsułoby
pytania, które dziś działają. Rzadkość sprawdzamy pomiarem w kolekcji, nie
zgadywaniem po wielkiej literze — użytkownik i tak pisze nazwiska z małej.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Rdzeń tokenu: krótszy niż pełne słowo, żeby złapać polską odmianę przy
# tokenizerze `prefix` („dynarską", „dynarskiej" → „dynars" ⊂ „dynarska").
DLUGOSC_RDZENIA = 6
MIN_DLUGOSC_SLOWA = 5
MAX_TERMINOW = 3

# Górna granica „rzadkości": udział fragmentów zawierających słowo. Powyżej niej
# słowo opisuje temat, a nie konkretny byt, i nie nadaje się na kryterium zakresu.
MAX_UDZIAL = 0.03
MIN_LIMIT = 20

# Słowa pospolite w pytaniach do bazy dokumentów: pytajniki, polecenia, nazwy
# rodzajów dokumentów i słowa opisujące samą aplikację. Nawet gdyby przeszły próg
# rzadkości, nie wskazują konkretnego bytu.
STOPY = {
    "jakie", "jaki", "jaka", "jakim", "czego", "czym", "kiedy", "gdzie", "dlaczego",
    "ktory", "który", "ktora", "która", "ktore", "które", "kogo", "komu",
    "wiesz", "powiedz", "pokaz", "pokaż", "znajdz", "znajdź", "wypisz", "podaj",
    "wyszukaj", "wylistuj", "opisz", "streszcz", "napisz",
    "dokument", "dokumenty", "dokumentow", "dokumentów", "dokumencie",
    "instrukcja", "instrukcje", "instrukcji", "instrukcjach",
    "procedura", "procedury", "procedurze", "zarzadzenie", "zarządzenie",
    "zarzadzenia", "zarządzenia", "regulamin", "regulaminu", "regulaminie",
    "wniosek", "wniosku", "wnioski", "zalacznik", "załącznik", "porozumienie",
    "praca", "pracy", "prace", "pracownik", "pracownika", "pracownicy",
    "zasady", "zasad", "zasadach", "przepisy", "przepisow", "przepisów",
    "informacje", "informacji", "temat", "tematu", "sprawie", "sprawa",
    "wszystkie", "wszystkich", "jakies", "jakieś", "moze", "może", "mozna", "można",
}


def _kandydaci(pytanie: str) -> list[tuple[str, bool]]:
    """Rdzenie dłuższych słów spoza listy pospolitych.

    Drugi element mówi, czy słowo było zapisane wielką literą W ŚRODKU zdania —
    to sygnał nazwy własnej. Pierwsze słowo pomijamy w tej ocenie, bo wielka litera
    na początku zdania nic nie znaczy.
    """
    slowa = re.findall(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", pytanie or "")
    wynik: list[tuple[str, bool]] = []
    widziane: set[str] = set()
    for i, slowo in enumerate(slowa):
        maly = slowo.lower()
        if len(maly) < MIN_DLUGOSC_SLOWA or maly in STOPY:
            continue
        rdzen = maly[:DLUGOSC_RDZENIA]
        if rdzen in widziane:
            continue
        widziane.add(rdzen)
        wynik.append((rdzen, i > 0 and slowo[:1].isupper()))
    return wynik


def terminy_selektywne(pytanie: str, policz, liczba_punktow: int,
                       znane_rdzenie: set[str] | None = None) -> list[str]:
    """Zwróć rdzenie słów, po których warto zawęzić wyszukiwanie.

    Słowo musi spełnić OBA warunki:
    1. wyglądać na nazwę własną — wielka litera w środku zdania albo obecność
       w rejestrze pól opisowych (`znane_rdzenie`); użytkownik pisze nazwiska
       z małej litery, więc sam rejestr jest tu ważniejszy niż zapis,
    2. być rzadkie w kolekcji — inaczej nie niesie informacji o zakresie.

    Bez warunku 1. przechodziłyby zwykłe słowa („stażowy", „zdalna", „pełni"),
    co zawężałoby pytania o treść, które dziś działają poprawnie.

    `policz(rdzen)` zwraca liczbę fragmentów ze słowem (None przy błędzie →
    słowo pomijamy, bo nie znamy jego rzadkości).
    """
    limit = max(MIN_LIMIT, int(liczba_punktow * MAX_UDZIAL)) if liczba_punktow else MIN_LIMIT
    znane = znane_rdzenie or set()
    wybrane: list[str] = []
    for rdzen, wielka_litera in _kandydaci(pytanie):
        if len(wybrane) >= MAX_TERMINOW:
            break
        if not wielka_litera and rdzen not in znane:
            continue
        ile = policz(rdzen)
        if ile is None or ile == 0 or ile > limit:
            continue
        wybrane.append(rdzen)
        logger.info(f"[CHAT-LEKS] '{rdzen}' w {ile} fragmentach (limit {limit}) → zawężam")
    return wybrane


def rdzenie_z_rejestru(db) -> set[str]:
    """Rdzenie słów występujących w polach opisowych dokumentów.

    Rejestr zna nazwiska osób opracowujących i zatwierdzających, organy wydające,
    numery i tytuły — czyli dokładnie te byty, o które użytkownik pyta z nazwy.
    Dzięki temu rozpoznajemy nazwisko także wtedy, gdy napisane jest z małej litery.
    """
    from app.models import File as FileModel

    rdzenie: set[str] = set()
    # UWAGA: wiersz z SQLAlchemy nie jest krotką (Row nie dziedziczy po tuple),
    # więc wartość kolumny bierzemy zawsze indeksem, a nie po sprawdzeniu typu.
    for rekord in db.query(FileModel.metadata_).all():
        meta = rekord[0]
        if not isinstance(meta, dict):
            continue
        for wartosc in (meta.get("doc_fields") or {}).values():
            if not isinstance(wartosc, str):
                continue
            for slowo in re.findall(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", wartosc):
                if len(slowo) >= MIN_DLUGOSC_SLOWA:
                    rdzenie.add(slowo.lower()[:DLUGOSC_RDZENIA])
    return rdzenie
