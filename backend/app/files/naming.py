"""Nazwy plików budowane z rozpoznanych pól dokumentu.

Po co: nazwy nadawane przez ludzi („1.pdf", „nr 3.pdf", „11.pdf") nie mówią nic
ani użytkownikowi na liście, ani modelowi w cytowaniu źródła — a w bazie ZCO
17 grup takich nazw oznacza RÓŻNE dokumenty. Skoro klasyfikacja rozpoznaje typ
dokumentu i wyciąga z niego pola, nazwa może z nich wynikać.

Wzorzec należy do TYPU dokumentu (`doc_type_schemas.name_pattern`), więc każda
kategoria ma własny: zarządzenie `{typ}-nr-{numer}-{data}`, umowa
`{typ}-{kontrahent}-{data}`. Wspólny jest tylko mechanizm podstawiania.

Moduł jest czysty — nie dotyka bazy ani dysku. Kolizje rozstrzyga wołający,
bo tylko on wie, jakie nazwy są już zajęte.
"""
import re

from app.text_utils import slugify

PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Nazwa pliku musi zmieścić się w limicie systemu plików (255 bajtów) razem
# z rozszerzeniem i ewentualnym sufiksem kolizji. 120 znaków to zapas z nawiązką,
# a jednocześnie nazwa, którą da się przeczytać na liście.
MAX_STEM = 120


def field_value(fields: dict, name: str) -> str:
    """Wartość pola dokumentu jako tekst; puste, gdy pola nie ma albo jest puste."""
    value = (fields or {}).get(name)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    return str(value).strip()


def missing_placeholders(pattern: str, doc_type: str, fields: dict) -> list[str]:
    """Nazwy pól, których wzorzec potrzebuje, a dokument ich nie ma.

    Braki są normalne — słaby OCR potrafi zgubić numer. Zwracamy je, żeby
    interfejs mógł pokazać „pominięty: brak pola numer" zamiast budować nazwę
    z dziurą w rodzaju `zarzadzenie-nr--2009`.
    """
    braki = []
    for nazwa in PLACEHOLDER.findall(pattern or ""):
        if nazwa == "typ":
            if not doc_type:
                braki.append("typ")
        elif not field_value(fields, nazwa):
            braki.append(nazwa)
    return braki


def build_filename(
    pattern: str,
    doc_type: str,
    fields: dict,
    extension: str,
) -> tuple[str | None, list[str]]:
    """(nazwa pliku, brakujące pola). Nazwa jest ``None``, gdy czegoś brakuje.

    `extension` podajemy z oryginalnej nazwy — wzorzec go nie zawiera, bo format
    pliku nie jest cechą dokumentu, tylko tego, jak go dostaliśmy.
    """
    if not (pattern or "").strip():
        return None, ["wzorzec"]

    braki = missing_placeholders(pattern, doc_type, fields)
    if braki:
        return None, braki

    def podstaw(m: re.Match) -> str:
        nazwa = m.group(1)
        surowa = doc_type if nazwa == "typ" else field_value(fields, nazwa)
        return slugify(surowa)

    rdzen = slugify(PLACEHOLDER.sub(podstaw, pattern), max_length=MAX_STEM)
    if not rdzen:
        return None, ["wzorzec"]

    ext = (extension or "").lstrip(".").lower()
    return (f"{rdzen}.{ext}" if ext else rdzen), []


def unique_filename(proposed: str, taken: set[str]) -> str:
    """Nazwa nieużywana jeszcze w zbiorze `taken`; przy kolizji dokłada `-2`, `-3`…

    Numer kolejny, a nie identyfikator dokumentu: użytkownik ma nazwę czytać,
    a `zarzadzenie-nr-1-2009-2` mówi mu więcej niż `zarzadzenie-nr-1-2009-e3f1a`.
    Kolizje są realne — tekst jednolity i zarządzenie zmieniające potrafią mieć
    ten sam numer i tę samą datę.
    """
    if proposed not in taken:
        return proposed
    rdzen, kropka, ext = proposed.rpartition(".")
    if not kropka:
        rdzen, ext = proposed, ""
    n = 2
    while True:
        kandydat = f"{rdzen}-{n}{'.' + ext if ext else ''}"
        if kandydat not in taken:
            return kandydat
        n += 1
