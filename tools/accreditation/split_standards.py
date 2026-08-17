"""Rozkłada dokument standardów akredytacyjnych na pojedyncze standardy.

Dlaczego skryptem, a nie modelem: dokument jest bazą danych wydrukowaną jako PDF.
Każdy standard ma ten sam szkielet — kod, tytuł wersalikami, trzy ponumerowane sekcje
i wagę na końcu. Podział jest więc zadaniem deterministycznym i nie ma powodu płacić
za nie modelowi ani ryzykować, że coś zmyśli. Model dostaje dopiero POJEDYNCZY standard
(około 2 kB) do zamiany na rekord — a to jest to samo zadanie, które `app/doc_extract.py`
wykonuje dziś na dokumentach klienta.

Źródłem MUSI być oryginalny PDF, nie fragmenty z bazy wektorowej: przy tych drugich kody
standardów (`PP 1`, `CO 3`) zachowały się tylko w 41 przypadkach na 223, bo parser nie
wciągnął elementu układu strony, w którym siedzą.

Uruchomienie:
    python split_standards.py <plik.pdf> [wynik.json]
"""
import json
import os
import re
import sys

import fitz  # PyMuPDF

# Kod standardu stoi w osobnej linii: dwie–trzy wielkie litery i numer („PP 1", „LŻ 12").
# Numer bywa HIERARCHICZNY („OS 1.2") — bez tego cały dział Ocena Stanu Zdrowia
# zwijał się do jednego standardu, bo kolejne po prostu nie były rozpoznawane.
KOD = re.compile(r"^([A-ZĄĆĘŁŃÓŚŹŻ]{2,3})\s?(\d{1,2}(?:\.\d{1,2})?)\s*$")

# Waga bywa zapisana z półpauzą albo z dywizem — w PDF-ie jest półpauza, w tekście
# z parsera dywiz. Przyjmujemy oba, żeby skrypt działał na obu źródłach.
WAGA = re.compile(r"Waga\s+standardu\s*[–-]\s*([\d,]+)")

# Sekcje wewnątrz standardu. Numeracja bywa rozdzielona tabulatorem.
SEKCJE = {
    "wymagania": re.compile(r"^1\.\s*\t?\s*Opis wymagań\s*$"),
    "sprawdzenie": re.compile(r"^2\.\s*\t?\s*Sposób sprawdzenia\s*$"),
    "punktacja": re.compile(r"^3\.\s*\t?\s*Ocena punktowa\s*$"),
}

# Wiersz rubryki punktowej to samotna cyfra (5, 3, 1), a opis jest pod nią.
PUNKT = re.compile(r"^([531])\s*$")

# Nagłówek strony: numer strony i tytuł opracowania, zawsze w pierwszych wierszach.
NAGLOWEK = re.compile(r"^(Standardy Akredytacyjne|\d{1,3})\s*$")


def czysty_tekst(pdf: str) -> list[str]:
    """Linie całego dokumentu, bez nagłówków stron.

    Nagłówek odcinamy WYŁĄCZNIE z początku strony. Pierwsza wersja tego filtru
    usuwała każdą linię będącą samą liczbą — i po cichu zjadała cyfry rubryki
    punktowej (5, 3 i 1 stoją w osobnych wierszach), przez co żaden standard
    nie dostał oceny punktowej. Numer strony wygląda dokładnie jak ocena;
    różni je wyłącznie położenie na stronie.
    """
    dokument = fitz.open(pdf)
    linie: list[str] = []
    for strona in dokument:
        surowe = [l.replace("\xa0", " ").rstrip() for l in strona.get_text("text").split("\n")]
        poczatek = 0
        while poczatek < len(surowe) and (not surowe[poczatek].strip()
                                          or NAGLOWEK.match(surowe[poczatek].strip())):
            poczatek += 1
        linie += [l for l in surowe[poczatek:] if l.strip()]
    return linie


def scal_przeniesienia(tekst: str) -> str:
    """Skleja wyrazy przeniesione na następny wiersz („zdrowot-\\nnej" → „zdrowotnej")."""
    tekst = re.sub(r"(\w)-\n(\w)", r"\1\2", tekst)
    return re.sub(r"\s*\n\s*", " ", tekst).strip()


def podziel(linie: list[str]) -> list[dict]:
    """Znajduje granice standardów po linii z kodem i tnie na bloki.

    Blok kończymy na linii z wagą, a nie na kodzie następnego standardu. Między
    standardami trafiają się strony tytułowe działów („PRAWA I OBOWIĄZKI PACJENTA")
    i wprowadzenia — doklejone do poprzedniego standardu zaśmiecałyby jego rubrykę
    punktową.
    """
    granice = [i for i, l in enumerate(linie) if KOD.match(l.strip())]
    bloki = []
    for nr, poczatek in enumerate(granice):
        limit = granice[nr + 1] if nr + 1 < len(granice) else len(linie)
        waga_na = next((i for i in range(poczatek, limit) if WAGA.search(linie[i])), None)
        # Kod bez wagi przed następnym kodem to nie standard, tylko pozycja spisu
        # treści albo odsyłacz w tekście.
        if waga_na is None:
            continue
        bloki.append(rozbierz(linie[poczatek:waga_na + 1]))
    return bloki


def rozbierz(blok: list[str]) -> dict:
    """Zamienia blok linii na rekord standardu."""
    m = KOD.match(blok[0].strip())
    # Numer zostaje NAPISEM, bo bywa hierarchiczny („1.2") — liczba by go spłaszczyła.
    dzial, numer = m.group(1), m.group(2)

    # Tytuł: wersaliki od drugiej linii do pierwszej sekcji.
    tytul_linie, i = [], 1
    while i < len(blok) and not any(w.match(blok[i].strip()) for w in SEKCJE.values()):
        tytul_linie.append(blok[i])
        i += 1
    tytul = scal_przeniesienia("\n".join(tytul_linie))

    # Znaczniki są częścią tytułu w nawiasie — wyjmujemy je do osobnych pól.
    obligatoryjny = "STANDARD OBLIGATORYJNY" in tytul
    wylaczalny = "MOŻE BYĆ WYŁĄCZONY" in tytul
    tytul_czysty = re.sub(r"\s*\((STANDARD [^)]*)\)\s*\.?\s*$", ".", tytul).strip()

    # Treść sekcji.
    sekcje: dict[str, list[str]] = {k: [] for k in SEKCJE}
    biezaca = None
    for linia in blok[i:]:
        s = linia.strip()
        trafiona = next((k for k, w in SEKCJE.items() if w.match(s)), None)
        if trafiona:
            biezaca = trafiona
            continue
        if WAGA.search(s):
            biezaca = None
            continue
        if biezaca:
            sekcje[biezaca].append(linia)

    waga = next((WAGA.search(l).group(1) for l in blok if WAGA.search(l)), None)

    return {
        "kod": f"{dzial} {numer}",
        "dzial": dzial,
        "numer": numer,
        "tytul": tytul_czysty,
        "obligatoryjny": obligatoryjny,
        "wylaczalny": wylaczalny,
        "waga": float(waga.replace(",", ".")) if waga else None,
        "wymagania": scal_przeniesienia("\n".join(sekcje["wymagania"])),
        "sposob_sprawdzenia": scal_przeniesienia("\n".join(sekcje["sprawdzenie"])),
        "punktacja": punktacja(sekcje["punktacja"]),
    }


def punktacja(linie: list[str]) -> dict[str, str]:
    """Rubryka 5/3/1 — dokument sam podaje, co zasługuje na ile punktów.

    To najcenniejsza część standardu dla przyszłego agenta: ocena przestaje być
    otwartym osądem, a staje się wyborem jednego z trzech opisanych wariantów.
    """
    wynik: dict[str, list[str]] = {}
    biezacy = None
    for linia in linie:
        s = linia.strip()
        if PUNKT.match(s):
            biezacy = s
            wynik[biezacy] = []
        elif biezacy:
            wynik[biezacy].append(linia)
    return {k: scal_przeniesienia("\n".join(v)) for k, v in wynik.items()}


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    pdf = sys.argv[1]
    wyjscie = sys.argv[2] if len(sys.argv) > 2 else "standardy.json"

    standardy = podziel(czysty_tekst(pdf))
    with open(wyjscie, "w", encoding="utf-8") as f:
        json.dump(standardy, f, ensure_ascii=False, indent=2)

    dzialy: dict[str, int] = {}
    for s in standardy:
        dzialy[s["dzial"]] = dzialy.get(s["dzial"], 0) + 1
    braki = {
        "bez wagi": sum(1 for s in standardy if s["waga"] is None),
        "bez wymagan": sum(1 for s in standardy if not s["wymagania"]),
        "bez punktacji": sum(1 for s in standardy if len(s["punktacja"]) < 3),
    }
    print(f"standardów: {len(standardy)} -> {os.path.basename(wyjscie)}")
    print("działy:", ", ".join(f"{k}={v}" for k, v in sorted(dzialy.items())))
    print("obligatoryjne:", sum(1 for s in standardy if s["obligatoryjny"]),
          "| wyłączalne:", sum(1 for s in standardy if s["wylaczalny"]))
    print("braki:", braki)


if __name__ == "__main__":
    main()
