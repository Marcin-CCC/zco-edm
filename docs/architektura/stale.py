"""Stałe i klocki rysunku (kolory, ramki, strzałki) — używa ich uklad.py."""

DATA = "31 lipca 2026"
WERSJA_APLIKACJI = "1.0.2"

GRANAT = "#1d2a4d"
TURKUS = "#0f9b8e"
NIEBIESKI = "#2563eb"
POMARANCZ = "#c2410c"
SZARY = "#64748b"
LINIA = "#cbd5e1"
TLO_KARTY = "#f8fafc"

SZEROKOSC, WYSOKOSC = 1680, 1190


def ramka(x, y, w, h, tytul, podtytul="", kolor=GRANAT, tlo="#ffffff", rw=10):
    """Kafelek: prostokąt z tytułem i opisem. W opisie „|” rozdziela wiersze."""
    t = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rw}" fill="{tlo}" '
         f'stroke="{kolor}" stroke-width="1.6"/>'
         f'<text x="{x + 14}" y="{y + 25}" font-size="15" font-weight="600" fill="{GRANAT}">'
         f'{tytul}</text>')
    for i, linia in enumerate(podtytul.split("|") if podtytul else []):
        t += (f'<text x="{x + 14}" y="{y + 45 + i * 16}" font-size="12" fill="{SZARY}">'
              f'{linia.strip()}</text>')
    return t


def strefa(x, y, w, h, tytul, opis, kolor):
    """Obszar zbiorczy (maszyna albo etap) — ramka przerywana z podpisem."""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="none" '
            f'stroke="{kolor}" stroke-width="2" stroke-dasharray="10 6" opacity="0.8"/>'
            f'<text x="{x + 20}" y="{y + 30}" font-size="19" font-weight="700" fill="{kolor}">'
            f'{tytul}</text>'
            + (f'<text x="{x + 20}" y="{y + 52}" font-size="13" fill="{SZARY}">{opis}</text>'
               if opis else ""))


def strzalka(x1, y1, x2, y2, etykieta="", kolor=GRANAT, przerywana=False):
    kreska = ' stroke-dasharray="7 5"' if przerywana else ""
    t = (f'<path d="M {x1} {y1} L {x2} {y2}" stroke="{kolor}" stroke-width="1.8" fill="none"'
         f'{kreska} marker-end="url(#grot-{kolor.lstrip("#")})"/>')
    if etykieta:
        sx, sy = (x1 + x2) / 2, (y1 + y2) / 2 - 7
        szer = len(etykieta) * 6.4 + 12
        t += (f'<rect x="{sx - szer / 2}" y="{sy - 12}" width="{szer}" height="17" rx="4" '
              f'fill="#ffffff" opacity="0.94"/>'
              f'<text x="{sx}" y="{sy}" font-size="11.5" fill="{kolor}" text-anchor="middle">'
              f'{etykieta}</text>')
    return t


def lamana(punkty, etykieta="", kolor=GRANAT, przerywana=False):
    """Strzałka łamana — dla połączeń prowadzonych korytarzem, z dala od kafelków."""
    kreska = ' stroke-dasharray="7 5"' if przerywana else ""
    d = "M " + " L ".join(f"{x} {y}" for x, y in punkty)
    t = (f'<path d="{d}" stroke="{kolor}" stroke-width="1.8" fill="none"{kreska} '
         f'marker-end="url(#grot-{kolor.lstrip("#")})"/>')
    if etykieta:
        (x1, y1), (x2, y2) = punkty[0], punkty[1]
        sx, sy = (x1 + x2) / 2, (y1 + y2) / 2 - 7
        szer = len(etykieta) * 6.4 + 12
        t += (f'<rect x="{sx - szer / 2}" y="{sy - 12}" width="{szer}" height="17" rx="4" '
              f'fill="#ffffff" opacity="0.94"/>'
              f'<text x="{sx}" y="{sy}" font-size="11.5" fill="{kolor}" text-anchor="middle">'
              f'{etykieta}</text>')
    return t
