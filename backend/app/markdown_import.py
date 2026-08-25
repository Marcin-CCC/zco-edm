"""Import plików Markdown z nagłówkiem YAML: pola dokumentu + PDF dla człowieka.

Po co osobna ścieżka dla `.md`: materiały od dostawców (opisy produktów pobrane
ze stron producentów) przychodzą jako Markdown z nagłówkiem, w którym pola są już
wypisane wprost. Dwie rzeczy wynikają z tego wprost:

* **Pola bierzemy z nagłówka, nie od modelu.** `doc_extract` istnieje dlatego, że
  zwykłe pismo ma nagłówek napisany prozą i trzeba go zrozumieć. Tutaj nie ma czego
  rozumieć — wartości są dokładne zamiast prawdopodobnych, import nie zajmuje kolejki
  vLLM (a to ona jest wąskim gardłem parsowania) i model nie „poprawi" nazwy produktu.
* **Człowiekowi pokazujemy PDF.** Plik `.md` z blokiem YAML na górze jest dla
  pielęgniarki nieczytelny, a przy cytowaniu odpowiedzi trzeba otworzyć coś, co da
  się przeczytać.

Do parsowania idzie WYGENEROWANY PDF, nie plik źródłowy. Dzięki temu przepływ n8n
zostaje nietknięty: jego `Switch` po rozszerzeniu widzi zwykły `pdf` i idzie
istniejącą gałęzią. Ten sam układ co przy `.odt`, gdzie obok źródła leży DOCX.

Markdown obsługujemy w zakresie, w jakim te pliki go używają — sprawdzone na całej
paczce 51 kart: nagłówek `#`, sekcje `##`, listy `- ` i akapity. Ani jednego
pogrubienia, odnośnika, tabeli czy bloku kodu. Nie piszemy parsera na zapas;
gdy pojawi się dostawca z bogatszym formatowaniem, dołożymy to, co realnie przyśle.
"""
import logging
import os
import re
from datetime import date, datetime

from fpdf import FPDF

logger = logging.getLogger(__name__)

KATALOG_CZCIONEK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Paleta z makiety zaakceptowanej przez użytkownika. Bursztynowy blok jest
# celowo wyrazisty: to jedyny element, który przetrwa wydrukowanie kartki
# i podanie jej dalej, a takie karty produktów krążą po oddziale.
GRANAT = (44, 44, 42)
SZARY = (95, 94, 90)
BURSZTYN_TLO = (250, 238, 218)
BURSZTYN_TEKST = (99, 56, 6)
BURSZTYN_OPIS = (133, 79, 11)
LINIA = (226, 232, 240)

MIESIACE = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
            "sierpnia", "września", "października", "listopada", "grudnia"]


# ==================== nagłówek YAML ====================

def _wartosc(surowa: str):
    """Zamienia zapis z nagłówka na wartość Pythona.

    Świadomie NIE wciągamy PyYAML: nagłówek jest generowany maszynowo i ma tylko
    napisy, `null`, liczby i płaskie listy. Pełny parser YAML to nowa zależność
    i nowa powierzchnia ataku (YAML potrafi konstruować obiekty) w miejscu, gdzie
    czytamy plik przysłany z zewnątrz.
    """
    s = (surowa or "").strip()
    if s in ("", "null", "~"):
        return None
    if s.startswith("[") and s.endswith("]"):
        srodek = s[1:-1].strip()
        if not srodek:
            return []
        return [_wartosc(cz) for cz in re.split(r",\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", srodek)]
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def podziel_naglowek(tekst: str) -> tuple[dict, str]:
    """Rozdziela nagłówek YAML od treści. Bez nagłówka zwraca ({}, cały tekst)."""
    tekst = tekst.lstrip("﻿")
    if not tekst.startswith("---"):
        return {}, tekst
    czesci = re.split(r"^---\s*$", tekst, maxsplit=2, flags=re.M)
    if len(czesci) < 3:
        return {}, tekst
    naglowek = {}
    for linia in czesci[1].splitlines():
        if not linia.strip() or linia.lstrip().startswith("#"):
            continue
        klucz, _, reszta = linia.partition(":")
        if not _:
            continue
        naglowek[klucz.strip()] = _wartosc(reszta)
    return naglowek, czesci[2].lstrip("\n")


# ==================== dane pochodne ====================

def nazwa_dostawcy(naglowek: dict) -> str | None:
    """Nazwa dostawcy: z nagłówka, a jak jej nie ma — z domeny adresu źródłowego."""
    jawna = naglowek.get("dostawca")
    if jawna:
        return str(jawna)
    adres = naglowek.get("zrodlo") or naglowek.get("url") or ""
    m = re.search(r"https?://(?:www\.)?([^/]+)", str(adres))
    if not m:
        return None
    domena = m.group(1).split(".")[0]
    return domena.capitalize() if domena else None


def _data(wartosc) -> date | None:
    if isinstance(wartosc, date):
        return wartosc
    try:
        return datetime.strptime(str(wartosc)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def data_slownie(wartosc) -> str | None:
    """2026-08-21 → „21 sierpnia 2026". Data ma być czytana, nie odcyfrowywana."""
    d = _data(wartosc)
    return f"{d.day} {MIESIACE[d.month - 1]} {d.year}" if d else None


def data_krotko(wartosc) -> str | None:
    d = _data(wartosc)
    return d.strftime("%d.%m.%Y") if d else None


def pola_dokumentu(naglowek: dict) -> dict:
    """Pola do zapisania w `files.metadata_["doc_fields"]`.

    Zwracamy WYŁĄCZNIE to, co ma sens w wyszukiwarce po polach. Klucze techniczne
    (`id`, `slug`, `jezyk`, `sekcje`, `liczba_chunkow`) zostają w pliku źródłowym —
    zaśmiecałyby ekran szczegółów, a nikt po nich nie szuka. Adres źródłowy też nie
    jest polem: część użytkowników ma zablokowane otwieranie stron z internetu,
    więc pole, którego nie da się użyć, tylko zajmowałoby miejsce. Adres widnieje
    w główce PDF-a.
    """
    pola = {}
    for klucz in ("kategoria", "producent", "pobrano"):
        wartosc = naglowek.get(klucz)
        if wartosc not in (None, ""):
            pola[klucz] = str(wartosc)
    dostawca = nazwa_dostawcy(naglowek)
    if dostawca:
        pola["dostawca"] = dostawca
    return pola


# ==================== przygotowanie plików ====================

# Znaki, których nie wolno wstawić do nazwy pliku. W nazwach produktów pojawiają się
# realnie: „Kliniderm Film / Kliniderm Film Roll" i „CoFlex TLC Zinc / Calamine".
_ZAKAZANE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def bezpieczna_nazwa(tekst: str, domyslna: str) -> str:
    """Nazwa produktu → nazwa pliku. Ukośnik zamieniamy na myślnik, nie usuwamy —
    „Film / Film Roll" ma zostać czytelne jako „Film - Film Roll"."""
    czysta = _ZAKAZANE.sub("-", (tekst or "").strip())
    czysta = re.sub(r"\s*-\s*", " - ", czysta)
    czysta = re.sub(r"\s+", " ", czysta).strip(" .")
    return czysta[:150] or domyslna


def typ_dokumentu(naglowek: dict, nazwy_schematow: dict) -> str | None:
    """Slug schematu dla tej karty — deterministycznie, bez pytania modelu.

    Dwie reguły, w tej kolejności:
    1. klucz `typ` w nagłówku wskazuje slug albo nazwę schematu,
    2. schemat o nazwie „Produkt <Dostawca>" — tak użytkownik nazywa typy per dostawca.

    Gdy żadna nie trafi, zwracamy None i typ ustala model jak dla każdego innego
    dokumentu. Pola z nagłówka i tak są już zapisane, więc model rozstrzyga wtedy
    wyłącznie rodzaj pisma.
    """
    szukane = []
    if naglowek.get("typ"):
        szukane.append(str(naglowek["typ"]))
    dostawca = nazwa_dostawcy(naglowek)
    if dostawca:
        szukane.append(f"Produkt {dostawca}")
    for kandydat in szukane:
        klucz = re.sub(r"[\s_-]+", "", kandydat.lower())
        for slug, nazwa in nazwy_schematow.items():
            if klucz in (re.sub(r"[\s_-]+", "", slug.lower()),
                         re.sub(r"[\s_-]+", "", (nazwa or "").lower())):
                return slug
    return None


def przygotuj(sciezka_md: str) -> dict:
    """Z pliku `.md` robi komplet do zapisania w bazie i wysłania do parsowania.

    Zwraca ścieżkę PDF-a, nazwę dokumentu, pola i nagłówek. PDF i źródło zostają
    obok siebie POD TYM SAMYM RDZENIEM nazwy — na tym założeniu opierają się
    zmiana nazwy pliku i sprzątanie przy usuwaniu (zob. `_zmien_nazwe_na_dysku`
    i `_derived_files` w files/router.py).
    """
    with open(sciezka_md, "r", encoding="utf-8-sig") as f:
        naglowek, tresc = podziel_naglowek(f.read())

    katalog = os.path.dirname(sciezka_md)
    zrodlowa_nazwa = os.path.basename(sciezka_md)
    rdzen = bezpieczna_nazwa(str(naglowek.get("nazwa") or ""),
                             os.path.splitext(zrodlowa_nazwa)[0])

    # Rdzeń bierzemy z nazwy produktu, żeby w Eksploratorze nie stał slug z adresu.
    docelowy_md = os.path.join(katalog, rdzen + ".md")
    if os.path.abspath(docelowy_md) != os.path.abspath(sciezka_md):
        os.replace(sciezka_md, docelowy_md)
    sciezka_pdf = os.path.join(katalog, rdzen + ".pdf")
    zbuduj_pdf(naglowek, tresc, sciezka_pdf)

    return {
        "naglowek": naglowek,
        "sciezka_md": docelowy_md,
        "sciezka_pdf": sciezka_pdf,
        "nazwa": rdzen + ".pdf",
        "nazwa_pierwotna": zrodlowa_nazwa,
        "pola": pola_dokumentu(naglowek),
    }


# ==================== PDF ====================

class _Dokument(FPDF):
    """Stopka powtarzana na każdej stronie — kartka wyrwana z pliku ma nadal mówić,
    z kiedy pochodzi treść i skąd."""

    def __init__(self, stopka_lewa: str):
        super().__init__(format="A4", unit="mm")
        self.stopka_lewa = stopka_lewa
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 18, 20)
        self.add_font("DejaVu", "", os.path.join(KATALOG_CZCIONEK, "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", os.path.join(KATALOG_CZCIONEK, "DejaVuSans-Bold.ttf"))

    def footer(self):
        self.set_y(-14)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*SZARY)
        self.cell(0, 5, self.stopka_lewa, align="L")
        self.set_x(-40)
        self.cell(20, 5, f"str. {self.page_no()} z {{nb}}", align="R")


def zbuduj_pdf(naglowek: dict, tresc: str, cel: str) -> str:
    """Renderuje kartę do PDF-a pod ścieżką `cel`. Zwraca tę ścieżkę."""
    dostawca = nazwa_dostawcy(naglowek)
    stan_na = data_krotko(naglowek.get("pobrano"))
    stopka = " · ".join(x for x in (dostawca, f"stan na {stan_na}" if stan_na else None) if x)

    pdf = _Dokument(stopka)
    pdf.add_page()
    szerokosc = pdf.w - pdf.l_margin - pdf.r_margin

    # --- nadtytuł: rodzaj materiału i dostawca
    nadtytul = " · ".join(x for x in (str(naglowek.get("typ") or "Karta produktu"), dostawca) if x)
    pdf.set_font("DejaVu", "", 7.5)
    pdf.set_text_color(*SZARY)
    pdf.cell(0, 4, nadtytul.upper(), new_x="LMARGIN", new_y="NEXT")

    # --- tytuł
    pdf.ln(1.5)
    pdf.set_font("DejaVu", "B", 15)
    pdf.set_text_color(*GRANAT)
    pdf.multi_cell(szerokosc, 7, str(naglowek.get("nazwa") or ""), new_x="LMARGIN", new_y="NEXT")

    # --- blok z datą ważności treści
    if stan_na:
        _blok_waznosci(pdf, szerokosc, data_slownie(naglowek.get("pobrano")),
                       zewnetrzny=bool(naglowek.get("zrodlo") or naglowek.get("url")))

    # --- metryczka
    _metryczka(pdf, szerokosc, naglowek)

    # --- treść
    _tresc(pdf, szerokosc, tresc)

    pdf.output(cel)
    return cel


def _blok_waznosci(pdf, szerokosc, data_tekst, zewnetrzny: bool):
    pdf.ln(3)
    opis = ("Materiał dostawcy pobrany ze strony producenta. "
            "Nie jest dokumentem organizacji.") if zewnetrzny else ""
    wysokosc = 13 if opis else 9
    y = pdf.get_y()
    pdf.set_fill_color(*BURSZTYN_TLO)
    pdf.rect(pdf.l_margin, y, szerokosc, wysokosc, style="F")
    pdf.set_xy(pdf.l_margin + 4, y + 2.5)
    pdf.set_font("DejaVu", "B", 10.5)
    pdf.set_text_color(*BURSZTYN_TEKST)
    pdf.cell(szerokosc - 8, 4.5, f"Stan na {data_tekst}", new_x="LMARGIN", new_y="NEXT")
    if opis:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font("DejaVu", "", 7.5)
        pdf.set_text_color(*BURSZTYN_OPIS)
        pdf.multi_cell(szerokosc - 8, 3.6, opis, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y + wysokosc + 4)


def _metryczka(pdf, szerokosc, naglowek):
    wiersze = [("Kategoria", naglowek.get("kategoria")),
               ("Producent", naglowek.get("producent")),
               ("Źródło", naglowek.get("url") or naglowek.get("zrodlo"))]
    for etykieta, wartosc in wiersze:
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*SZARY)
        pdf.cell(24, 4.6, etykieta)
        pdf.set_text_color(*GRANAT)
        # Adres bywa dłuższy niż wiersz i nie ma w nim spacji, po których dałoby się
        # złamać — `multi_cell` łamie wtedy po znakach, zamiast wyjechać poza margines.
        pdf.multi_cell(szerokosc - 24, 4.6, str(wartosc) if wartosc else "—",
                       new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_draw_color(*LINIA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + szerokosc, pdf.get_y())
    pdf.ln(3)


def _tresc(pdf, szerokosc, tresc: str):
    """Markdown w zakresie, jakiego używają te pliki: `##` sekcje, `- ` listy, akapity.

    Nagłówek `#` pomijamy — to powtórzenie nazwy produktu, która stoi już w tytule.
    """
    for linia in tresc.splitlines():
        linia = linia.rstrip()
        if not linia:
            continue
        if linia.startswith("# "):
            continue
        if linia.startswith("## "):
            pdf.ln(2)
            pdf.set_font("DejaVu", "B", 10.5)
            pdf.set_text_color(*GRANAT)
            pdf.multi_cell(szerokosc, 5.5, linia[3:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.5)
        elif re.match(r"^[-*+]\s+", linia):
            pdf.set_font("DejaVu", "", 9)
            pdf.set_text_color(*SZARY)
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(szerokosc - 3, 4.6, "•  " + re.sub(r"^[-*+]\s+", "", linia),
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("DejaVu", "", 9)
            pdf.set_text_color(*SZARY)
            pdf.multi_cell(szerokosc, 4.6, linia, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
