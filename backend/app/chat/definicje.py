"""Pytania definicyjne — te, przy których historia rozmowy szkodzi.

Zmierzone na instancji demo (2026-08-06), 5 powtórzeń każdego wariantu:

    „rozwiń skrót zco" BEZ historii            → odmowa 5/5
    „rozwiń skrót zco" Z historią o PPK        → wymyślona odpowiedź 5/5
        „Związek Członkowskiego Ośrodka", „Zespół Częściowo Ograniczony",
        „Zarządca Centrum Oświaty" — za każdym razem inna, czyli czyste zgadywanie

Ten sam kontekst z dokumentów, ta sama konfiguracja; jedyną zmienną jest historia.
Mechanizm: skoro w poprzedniej turze padło „…PPK w zco…", model traktuje skrót jak
byt już ustalony w rozmowie i czuje się w obowiązku go rozwinąć. Dokumenty milczą,
więc rozwinięcie bierze z własnej wiedzy — wbrew zakazowi w prompcie.

Dlatego przy pytaniu O ZNACZENIE POJĘCIA historii nie wysyłamy. Odpowiedź ma wtedy
jedno źródło: treść dokumentów. Jeśli ich nie ma, model odmawia — i tak ma być.

UWAGA na drugą stronę: „co to jest ten dokument?" TEŻ jest pytaniem definicyjnym,
ale o byt wskazany w rozmowie — bez historii stałoby się bez sensu. Rozstrzyga więc
nie sama forma pytania, tylko czy pytamy o KONKRETNE pojęcie, czy o coś, na co
wskazuje poprzednia tura.
"""

import re

# Formy, którymi pytamy o znaczenie pojęcia
_FORMY = re.compile(
    r"^\s*(?:"
    r"co\s+to\s+(?:jest|za|znaczy|oznacza)|"
    r"co\s+oznacza|co\s+znaczy|"
    r"czym\s+(?:jest|są|sa)|"
    r"rozwi[nń]\s+skr[oó]t|jak\s+rozwin[aą][cć]\s+skr[oó]t|"
    r"co\s+kryje\s+si[eę]\s+pod\s+skr[oó]tem|"
    r"skr[oó]t\s+od|definicja|znaczenie\s+skr[oó]tu"
    r")\b",
    re.IGNORECASE,
)

# Słowa, które NIE nazywają pojęcia, tylko wskazują na coś z rozmowy
_ODWOLANIA = {
    "ten", "ta", "to", "te", "ci", "tego", "tej", "tym", "tych", "temu", "tamten",
    "nim", "nich", "niego", "niej", "nimi", "je", "go", "ich", "jego", "jej",
    "powyzszy", "powyższy", "powyzsze", "powyższe", "taki", "taka", "takie",
    "on", "ona", "ono", "oni", "one", "sam", "sama", "samo",
    "mnie", "mi", "ja", "nas", "nam", "ciebie", "tobie", "was", "wam",
}

# Nazwy KATEGORII dokumentów. Same z siebie nie nazywają pojęcia — „co to za dokument"
# pyta o coś pokazanego w rozmowie, dopiero „co to za dokument F-303" o konkret.
_KATEGORIE = {
    "dokument", "dokumentu", "dokumenty", "plik", "pliku", "pliki", "pismo", "pisma",
    "procedura", "procedury", "instrukcja", "instrukcji", "zarzadzenie", "zarządzenie",
    "regulamin", "regulaminu", "wniosek", "wniosku", "formularz", "formularza",
    "sprawa", "sprawy", "temat", "tematu", "rzecz", "rzeczy", "tekst", "tekstu", "akt",
}

# Wyrazy pomocnicze bez własnej treści — nie liczą się jako nazwa pojęcia
_NIEISTOTNE = {"w", "we", "z", "ze", "na", "do", "o", "od", "po", "przy", "dla", "i",
               "oraz", "a", "czy", "jest", "są", "sa", "sie", "się"}


def pytanie_definicyjne(tresc: str) -> bool:
    """Czy to pytanie O ZNACZENIE konkretnego pojęcia (a nie o byt z rozmowy).

    True  → „co to jest PPK", „rozwiń skrót ZCO", „czym jest dodatek stażowy"
    False → „co to jest ten dokument", „co to znaczy", „jak rozliczyć delegację"
    """
    tekst = (tresc or "").strip()
    if not _FORMY.match(tekst):
        return False

    reszta = _FORMY.sub("", tekst, count=1)
    slowa = [s.strip(".,;:!?\"'()„”-").lower() for s in reszta.split()]
    # Zostaje to, co MOŻE nazywać pojęcie: bez wyrazów pomocniczych, bez wskazań
    # na rozmowę i bez samych nazw kategorii dokumentów.
    nazwa = [s for s in slowa
             if s and s not in _NIEISTOTNE and s not in _ODWOLANIA and s not in _KATEGORIE]
    return bool(nazwa)
