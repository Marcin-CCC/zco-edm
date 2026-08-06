"""Skróty, których nie ma w dokumentach — najczęstsze źródło zmyśleń.

Zmierzone na instancji demo (2026-08-06), pytanie „czy mogę przystąpić do PPK w ZCO?",
gdzie „PPK" jest w dokumentach, a „ZCO" nie ma wcale:

    bez ostrzeżenia   → wymyślone rozwinięcie w 4 na 6 prób
                        „Zakład Częściowego Odpowiedzialności", „Zakład Centralny
                        Ochrony", „Związek Chorobowy Ochrony" — za każdym razem inne,
                        z doklejonymi „faktami" (data startu PPK, status jednostki)
    z ostrzeżeniem    → 0 na 6, przy zachowaniu odpowiedzi na resztę pytania

Dlaczego akurat skróty: sprawdzone na podstawionych bytach — „XYZ" model odrzuca,
a „ACME", „Fundacja Kowalskiego" czy „Szpital Miejski w Koninie" dostają uczciwą
odpowiedź warunkową („o ile spełniasz warunki uczestnictwa"). Przymus wyjaśnienia
uruchamia dopiero skrót WYGLĄDAJĄCY NA SENSOWNY — bo skrót się rozwija, a nazwy nie.

Ostrzeżenie dopisujemy do treści wiadomości, nie do promptu — dzięki temu zmiana
żyje w kodzie (z testami i historią), a nie w konfiguracji n8n wymagającej publikacji.

Sprawdzone warianty brzmienia (5 prób każdy): sam zakaz zgadywania działa, ale model
odmawia wtedy CAŁEGO pytania (5/5), tracąc odpowiedź na część, która w dokumentach
jest. Dlatego ostrzeżenie musi zawierać oba polecenia: nie zgaduj — i odpowiedz
na resztę.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Skrót: 2–8 znaków, same wielkie litery (z polskimi), opcjonalnie z cyframi (L4, ZFŚS).
# Krótsze niż 2 znaki to szum, dłuższe to zwykle wyraz pisany wersalikami.
_SKROT = re.compile(r"\b[A-ZŁŚŻŹĆŃÓĄĘ][A-ZŁŚŻŹĆŃÓĄĘ0-9]{1,7}\b")

# Wersaliki, które skrótami nie są (użytkownik krzyczy albo pisze nazwę własną)
_NIE_SKROTY = {"NIE", "TAK", "ORAZ", "JAK", "CZY", "CO", "KTO", "GDZIE", "KIEDY",
               "MAM", "MOGE", "MOGĘ", "CHCE", "CHCĘ", "PROSZE", "PROSZĘ"}

MAX_SKROTOW = 3   # więcej i tak nie zmieści się sensownie w ostrzeżeniu


def skroty_z_pytania(tresc: str) -> list[str]:
    """Skróty użyte w pytaniu, w kolejności wystąpienia, bez powtórzeń."""
    znalezione: list[str] = []
    for m in _SKROT.finditer(tresc or ""):
        s = m.group(0)
        if s in _NIE_SKROTY or s in znalezione:
            continue
        znalezione.append(s)
    return znalezione


def nieznane_skroty(tresc: str, policz) -> list[str]:
    """Skróty z pytania, których NIE MA w dokumentach tej instancji.

    `policz(term)` zwraca liczbę fragmentów zawierających słowo (None przy awarii —
    wtedy skrót pomijamy, bo nie wiemy, czy jest w bazie; lepiej nie ostrzegać
    niepotrzebnie niż ostrzec fałszywie).
    """
    wynik: list[str] = []
    for s in skroty_z_pytania(tresc):
        if len(wynik) >= MAX_SKROTOW:
            break
        ile = policz(s.lower())
        if ile == 0:
            wynik.append(s)
    return wynik


def uwaga_o_skrotach(skroty: list[str]) -> str:
    """Ostrzeżenie doklejane do wiadomości. Puste, gdy nie ma czego ostrzegać.

    Brzmienie wybrane pomiarowo (zob. docstring modułu): musi zakazać zgadywania
    ORAZ nakazać odpowiedź na pozostałą część pytania.
    """
    if not skroty:
        return ""
    lista = ", ".join(f'„{s}"' for s in skroty)
    czego = "tych skrótów" if len(skroty) > 1 else "tego skrótu"
    return (
        f"\n\n[Uwaga: dokumenty nie zawierają żadnej wzmianki o {lista}. "
        f"Potraktuj pytanie tak, jakby nie zawierało {czego}: odpowiedz na jego pozostałą "
        f"część na podstawie dokumentów. O samym {lista} napisz jedynie, że dokumenty go "
        f"nie opisują. Nie zgaduj, co oznacza.]"
    )
