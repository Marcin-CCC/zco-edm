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

# W dziale PAT kod stoi w JEDNEJ linii z tytułem. Rozpoznajemy to po tym, że dalej
# idą wersaliki — w spisie treści działu tytuł jest zdaniowy, więc wielkość liter
# odróżnia prawdziwy standard od pozycji spisu.
KOD_Z_TYTULEM = re.compile(
    r"^([A-ZĄĆĘŁŃÓŚŹŻ]{2,3})\s(\d{1,2}(?:\.\d{1,2})?)\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ\s,\-–()/%\.]{10,}.*)$"
)


def dopasuj_kod(linia: str):
    """Zwraca (dział, numer, reszta_linii) albo None."""
    s = linia.strip()
    m = KOD.match(s)
    if m:
        return m.group(1), m.group(2), ""
    m = KOD_Z_TYTULEM.match(s)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None

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
    return scal_rozbite_kody(linie)


# Same litery działu w jednej linii i sam numer w następnej — tak złożony jest
# dział PAT. Bez scalenia jego standardy nie mają rozpoznawalnego kodu i wypadają
# z rejestru razem z całą treścią.
SAME_LITERY = re.compile(r"^[A-ZĄĆĘŁŃÓŚŹŻ]{2,3}$")
SAM_NUMER = re.compile(r"^\d{1,2}(?:\.\d{1,2})?$")


def scal_rozbite_kody(linie: list[str]) -> list[str]:
    """Skleja kod rozbity na dwie linie („PAT" + „2.2" → „PAT 2.2")."""
    wynik: list[str] = []
    i = 0
    while i < len(linie):
        biezaca = linie[i].strip()
        nastepna = linie[i + 1].strip() if i + 1 < len(linie) else ""
        if SAME_LITERY.match(biezaca) and SAM_NUMER.match(nastepna):
            wynik.append(f"{biezaca} {nastepna}")
            i += 2
            continue
        wynik.append(linie[i])
        i += 1
    return wynik


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
    granice = [i for i, l in enumerate(linie) if dopasuj_kod(l)]
    bloki = []
    for nr, poczatek in enumerate(granice):
        limit = granice[nr + 1] if nr + 1 < len(granice) else len(linie)
        if not zawiera_standard(linie, poczatek, limit):
            continue
        # Blok kończymy na wadze, gdy jest — po niej idą już strony tytułowe działów
        # i wprowadzenia. Gdy wagi brak, bierzemy cały zakres do następnego kodu.
        waga_na = next((i for i in range(poczatek, limit) if WAGA.search(linie[i])), None)
        koniec = waga_na + 1 if waga_na is not None else limit
        bloki.append(rozbierz(linie[poczatek:koniec]))
    return bloki


def zawiera_standard(linie: list[str], poczatek: int, limit: int) -> bool:
    """Czy w zakresie DO NASTĘPNEGO KODU stoi opis wymagań.

    To jest definicja standardu w tym dokumencie. Wcześniej wymagaliśmy wagi i było
    to błędne z dwóch stron: nagłówki grup („KZ 1", którego treść niosą dzieci
    KZ 1.1, KZ 1.2…) trafiały albo nie trafiały do rejestru przypadkiem, a standardy
    bez wagi wypadały mimo pełnej treści. Waga jest metadaną, nie definicją.

    Zakres liczony do NASTĘPNEGO kodu, nie „kilkanaście linii w przód" — inaczej
    nagłówek grupy zagarnia „Opis wymagań" należący do swojego pierwszego dziecka.
    """
    return any(SEKCJE["wymagania"].match(l.strip()) for l in linie[poczatek:limit])


def rozbierz(blok: list[str]) -> dict:
    """Zamienia blok linii na rekord standardu."""
    # Numer zostaje NAPISEM, bo bywa hierarchiczny („1.2") — liczba by go spłaszczyła.
    dzial, numer, reszta = dopasuj_kod(blok[0])

    # Tytuł: wersaliki od drugiej linii do pierwszej sekcji. Gdy kod stał w jednej
    # linii z tytułem (dział PAT), pierwszy kawałek tytułu jest już w `reszta`.
    tytul_linie, i = ([reszta] if reszta else []), 1
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


# Spis standardów na stronie tytułowej działu: kod i tytuł zdaniowy w jednej linii.
# To jest NIEZALEŻNE od nas źródło prawdy o tym, ile standardów ma dokument.
SPIS_DZIALU = re.compile(
    r"^([A-ZĄĆĘŁŃÓŚŹŻ]{2,3})\s(\d{1,2}(?:\.\d{1,2})?)\s+([A-ZĄĆĘŁŃÓŚŹŻ][^\n]{15,})$", re.M)


def sprawdz_kompletnosc(linie: list[str], standardy: list[dict]) -> dict:
    """Porównuje rejestr ze spisami działów zawartymi w samym dokumencie.

    Bez tego jedyną miarą byłaby liczba znaczników wagi — czyli nasz własny wskaźnik
    zastępczy. Spisy działów są od nas niezależne i mówią wprost, ile standardów
    dokument deklaruje.

    Kod obecny w spisie, a nieobecny w rejestrze, bywa NAGŁÓWKIEM GRUPY („KZ 1",
    którego treść niosą dzieci KZ 1.1…) — taki nie ma własnego „Opisu wymagań"
    i słusznie nie jest rekordem. Rozróżniamy te dwa przypadki, bo tylko drugi
    jest błędem.
    """
    caly = "\n".join(linie)
    oczekiwane = {f"{m.group(1)} {m.group(2)}" for m in SPIS_DZIALU.finditer(caly)}
    mamy = {s["kod"] for s in standardy}

    # Ta sama definicja co przy podziale — inaczej kontrola sprawdzałaby co innego,
    # niż robi parser, i potrafiłaby dać wynik odwrotny do prawdy.
    granice = [i for i, l in enumerate(linie) if dopasuj_kod(l)]
    naglowki, zgubione = [], []
    for kod in sorted(oczekiwane - mamy):
        ma_tresc = False
        for nr, i in enumerate(granice):
            d, n, _ = dopasuj_kod(linie[i])
            if f"{d} {n}" != kod:
                continue
            limit = granice[nr + 1] if nr + 1 < len(granice) else len(linie)
            if zawiera_standard(linie, i, limit):
                ma_tresc = True
                break
        (zgubione if ma_tresc else naglowki).append(kod)

    return {
        "w_spisach": len(oczekiwane),
        "w_rejestrze": len(mamy),
        "naglowki_grup": naglowki,
        "zgubione": zgubione,
        "spoza_spisow": sorted(mamy - oczekiwane),
    }


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    pdf = sys.argv[1]
    wyjscie = sys.argv[2] if len(sys.argv) > 2 else "standardy.json"

    linie = czysty_tekst(pdf)
    standardy = podziel(linie)
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
    print("niepełne rekordy:", braki)

    k = sprawdz_kompletnosc(linie, standardy)
    print(f"\nkontrola wobec spisów działów: {k['w_rejestrze']} z {k['w_spisach']} kodów")
    print(f"  nagłówki grup (poprawnie pominięte): {len(k['naglowki_grup'])}"
          f" — {', '.join(k['naglowki_grup'])}")
    print(f"  spoza spisów: {', '.join(k['spoza_spisow']) or 'brak'}")
    if k["zgubione"]:
        print(f"  !!! ZGUBIONE STANDARDY: {', '.join(k['zgubione'])}")
        raise SystemExit(1)
    print("  zgubionych standardów: brak")


if __name__ == "__main__":
    main()
