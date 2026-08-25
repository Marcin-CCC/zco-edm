"""Języki interfejsu — jedno miejsce, z którego korzystają backend i front.

Polski jest językiem BAZOWYM: w nim powstają teksty i on jest zapasem, gdy dla innego
języka brakuje tłumaczenia. Interfejs pokazuje kody ISO 639-1 (`PL`, `EN`).

Skąd bierze się język zalogowanej osoby, w tej kolejności:

1. `users.locale` — wybór konkretnego konta (NULL = brak wyboru),
2. `DEFAULT_LOCALE` — domyślny dla wdrożenia (ZCO chodzi po polsku, demo anglojęzyczne
   mogłoby startować po angielsku bez zmiany kodu),
3. polski.

Języka PRZEGLĄDARKI świadomie nie pytamy. Na komputerze na oddziale konto bywa wspólne
albo przeglądarka ustawiona przez kogoś innego, więc interfejs zmieniałby język między
zmianami bez niczyjej decyzji.
"""

import os

# Kod bazowy. Nie jest „jednym z" — dla pozostałych języków jest wartością zapasową.
BASE_LOCALE = "pl"

# Kolejność ma znaczenie: tak samo idą przyciski w przełączniku.
SUPPORTED_LOCALES: tuple[str, ...] = ("pl", "en")


def normalize_locale(value: str | None) -> str | None:
    """Kod w postaci używanej w bazie albo None, gdy nie rozpoznajemy.

    Przyjmujemy zapisy, które przychodzą z przeglądarek i nagłówków — `EN`, `en-US`,
    `en_GB` — i sprowadzamy je do samego języka. Wartości spoza listy odrzucamy,
    zamiast zapisywać: kolumna `locale` steruje wyborem katalogu tłumaczeń i wpis
    typu `de` bez katalogu zostawiłby użytkownika z pustym interfejsem.
    """
    if not value:
        return None
    kod = value.strip().replace("_", "-").split("-")[0].lower()
    return kod if kod in SUPPORTED_LOCALES else None


def default_locale() -> str:
    """Domyślny język wdrożenia. Błędna wartość w środowisku nie może wywrócić startu."""
    return normalize_locale(os.getenv("DEFAULT_LOCALE")) or BASE_LOCALE
