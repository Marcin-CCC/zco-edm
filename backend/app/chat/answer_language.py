"""Język, w którym model ma napisać odpowiedź.

Model po poinstruowaniu odpowiada w zadanym języku bez problemu — sprawdzone.
Sęk w tym, KIEDY go instruować i co przy tym zastrzec.

**Warunkowo.** Instrukcję dokładamy wyłącznie wtedy, gdy język interfejsu różni się
od polskiego. Dla osoby pracującej po polsku byłaby to sama strata: kilkadziesiąt
tokenów promptu na powiedzenie modelowi, żeby robił to, co i tak robi, plus ryzyko,
że zacznie tłumaczyć cytowane wartości z dokumentów.

**Zastrzeżenie o dokumentach.** Kontekst jest w innym języku niż odpowiedź i model
musi o tym wiedzieć, inaczej bierze to za pomyłkę i albo przechodzi na język
dokumentów, albo tłumaczy numery i nazwy własne. Zbiór NIE jest jednojęzyczny —
materiały od dostawców bywają po angielsku — więc mówimy „najczęściej polskim",
a nie „polskim".

**Czego NIE wolno tłumaczyć.** Nazwy plików, numery dokumentów, oznaczenia norm
i cytowane wartości liczbowe. Przetłumaczona nazwa pliku przestaje pasować do
listy źródeł pod odpowiedzią, a przetłumaczony numer zarządzenia jest po prostu
nieprawdziwy.

Instrukcja powstaje TUTAJ, a nie w n8n: dzięki temu zmiana jej brzmienia nie wymaga
edycji workflow i kliknięcia „Publish". n8n tylko wstawia gotowy tekst w prompt.
Sam tekst jest po polsku, bo po polsku jest cały prompt systemowy — model dostaje
wtedy jeden spójny zestaw poleceń.
"""

from app.locales import BASE_LOCALE, normalize_locale

# Nazwa języka w MIANOWNIKU, do wstawienia w polecenie.
NAZWY_JEZYKOW = {
    "en": "angielskim",
    "cs": "czeskim",
    "de": "niemieckim",
    "es": "hiszpańskim",
    "uk": "ukraińskim",
}

_SZABLON = """
## Język odpowiedzi (NADRZĘDNE wobec języka Kontekstu)

- Całą odpowiedź napisz w języku {jezyk}. Dotyczy to także zdania o braku informacji.
- Kontekst jest w innym języku (najczęściej polskim). To NIE jest pomyłka — nie
  przechodź na język dokumentów i nie komentuj tej różnicy.
- NIE tłumacz: nazw plików, numerów dokumentów, oznaczeń norm, dat ani cytowanych
  wartości liczbowych. Przepisz je dokładnie tak, jak stoją w Kontekście.
- Znaczniki cytowań przepisz bez zmian — są identyczne w każdym języku.
"""


def language_instruction(locale: str | None) -> str:
    """Fragment promptu dla n8n. Pusty, gdy odpowiedź ma być po polsku.

    Nierozpoznany kod traktujemy jak brak wyboru: lepiej odpowiedź po polsku niż
    polecenie „odpowiadaj w języku None".
    """
    kod = normalize_locale(locale)
    if kod is None or kod == BASE_LOCALE:
        return ""
    nazwa = NAZWY_JEZYKOW.get(kod)
    if nazwa is None:                 # język na liście, ale bez nazwy — nie zgadujemy
        return ""
    return _SZABLON.format(jezyk=nazwa)
