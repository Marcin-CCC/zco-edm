"""Drobne operacje na tekście używane w kilku miejscach naraz.

Powstał, gdy ta sama transliteracja polskich znaków była już w trzech modułach
(dobór fragmentów, kody ról, nazwy plików). Trzy kopie tej samej tablicy to trzy
miejsca, w których można zapomnieć o „ż".
"""
import re

_DIACRITICS = str.maketrans("ąćęłńóśźż", "acelnoszz")


def strip_diacritics(text: str) -> str:
    """Pisownia bez znaków diakrytycznych, małymi literami."""
    return (text or "").lower().translate(_DIACRITICS)


def slugify(text: str, separator: str = "-", max_length: int = 0) -> str:
    """Tekst sprowadzony do `a-z0-9` i separatora — bezpieczny w nazwie pliku.

    Zakazane znaki systemu plików (`\\ / : * ? " < > |`) znikają razem z resztą
    interpunkcji, więc nie trzeba ich wymieniać osobno. Cyfry i myślniki zostają,
    dzięki czemu data w formacie ISO (`2009-01-09`) przechodzi bez zmian.
    """
    base = strip_diacritics(text)
    base = re.sub(r"[^a-z0-9]+", separator, base)
    base = re.sub(re.escape(separator) + r"{2,}", separator, base).strip(separator)
    if max_length and len(base) > max_length:
        base = base[:max_length].rstrip(separator)
    return base
