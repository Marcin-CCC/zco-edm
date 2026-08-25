"""Testy importu plików Markdown z nagłówkiem YAML (materiały od dostawców).

Uruchom: pytest backend/tests/test_markdown_import.py -v

Co jest tu pilnowane i dlaczego akurat to:

* **Nagłówek czytamy sami, bez PyYAML.** Parser własny musi radzić sobie z tym,
  co realnie przysyłają skrypty: `null`, listy, cudzysłowy, polskie znaki.
* **Rdzeń nazwy wspólny dla `.md` i `.pdf`.** Na tym założeniu opierają się zmiana
  nazwy pliku i sprzątanie przy usuwaniu (`_derived_files` w files/router.py).
  Rozjechanie rdzeni zostawiłoby po usunięciu osieroconą połówkę pary.
* **Data ważności trafia do pól.** To ona rozstrzyga, czy czytelnik wie, z kiedy
  są dane — a data dodania pliku mówi co innego.
"""
import os

import pytest

from app.markdown_import import (bezpieczna_nazwa, data_slownie, nazwa_dostawcy,
                                 podziel_naglowek, pola_dokumentu, przygotuj,
                                 typ_dokumentu, zbuduj_pdf)

KARTA = """---
id: "aspironix:actisorb-plus-25"
slug: "actisorb-plus-25"
nazwa: "ACTISORB PLUS 25 opatrunek z węglem aktywowanym i srebrem"
kategoria: "Opatrunki nowoczesne"
producent: null
url: "https://www.aspironix.pl/produkt/actisorb-plus-25/"
zrodlo: "https://www.aspironix.pl/produkty/"
jezyk: "pl"
pobrano: "2026-08-21"
sekcje: ["Opis", "Działanie"]
liczba_chunkow: 5
---

# ACTISORB PLUS 25

## Opis

Opatrunek wykazuje skuteczne działanie przeciwko drobnoustrojom.

## Działanie

- oczyszcza rany zainfekowane
- pochłania nieprzyjemny zapach
"""


class TestNaglowka:
    def test_klucze_i_typy(self):
        naglowek, tresc = podziel_naglowek(KARTA)
        assert naglowek["nazwa"].startswith("ACTISORB")
        assert naglowek["producent"] is None, "`null` ma być None, nie napisem „null”"
        assert naglowek["liczba_chunkow"] == 5
        assert naglowek["sekcje"] == ["Opis", "Działanie"]
        assert tresc.startswith("# ACTISORB")

    def test_plik_bez_naglowka_zostaje_trescia(self):
        naglowek, tresc = podziel_naglowek("# Zwykły markdown\n\ntreść")
        assert naglowek == {} and tresc.startswith("# Zwykły")

    def test_bom_na_poczatku_nie_psuje_naglowka(self):
        """Pliki z Windows potrafią zaczynać się znacznikiem kolejności bajtów."""
        naglowek, _ = podziel_naglowek("﻿" + KARTA)
        assert naglowek.get("slug") == "actisorb-plus-25"

    def test_niedomkniety_naglowek_nie_wywraca(self):
        naglowek, tresc = podziel_naglowek("---\nnazwa: \"X\"\n\nbrak zamkniecia")
        assert naglowek == {} and "brak zamkniecia" in tresc


class TestPolDokumentu:
    def test_tylko_pola_uzyteczne_w_wyszukiwaniu(self):
        """Klucze techniczne (`id`, `slug`, `jezyk`, `sekcje`) tylko zaśmiecałyby
        ekran szczegółów — nikt po nich nie szuka."""
        pola = pola_dokumentu(podziel_naglowek(KARTA)[0])
        assert set(pola) == {"kategoria", "pobrano", "dostawca"}

    def test_puste_producent_nie_tworzy_pola(self):
        assert "producent" not in pola_dokumentu(podziel_naglowek(KARTA)[0])

    def test_url_nie_jest_polem(self):
        """Decyzja użytkownika: część odbiorców ma zablokowane otwieranie stron,
        więc adres zostaje w główce PDF-a, a nie w polach do filtrowania."""
        assert "url" not in pola_dokumentu(podziel_naglowek(KARTA)[0])

    def test_dostawca_z_domeny_gdy_brak_jawnego(self):
        assert nazwa_dostawcy(podziel_naglowek(KARTA)[0]) == "Aspironix"

    def test_dostawca_jawny_ma_pierwszenstwo(self):
        assert nazwa_dostawcy({"dostawca": "Schulke", "zrodlo": "https://aspironix.pl/"}) == "Schulke"


class TestNazwyPlikow:
    @pytest.mark.parametrize("nazwa,oczekiwana", [
        ("Kliniderm Film / Kliniderm Film Roll", "Kliniderm Film - Kliniderm Film Roll"),
        ("V.A.C ® GranuFoam ™", "V.A.C ® GranuFoam ™"),
        ("CoFlex TLC Zinc / Calamine", "CoFlex TLC Zinc - Calamine"),
    ])
    def test_znaki_zakazane_zamieniane_nie_usuwane(self, nazwa, oczekiwana):
        """Ukośnik jest częścią nazwy handlowej — po wycięciu zostałoby „Film Film Roll”."""
        assert bezpieczna_nazwa(nazwa, "zapas") == oczekiwana

    def test_pusta_nazwa_wraca_do_zapasowej(self):
        assert bezpieczna_nazwa("", "slug-z-adresu") == "slug-z-adresu"

    def test_nazwa_przycieta_do_rozsadnej_dlugosci(self):
        assert len(bezpieczna_nazwa("x" * 400, "zapas")) <= 150


class TestTypuDokumentu:
    def test_dopasowanie_po_wzorcu_produkt_dostawca(self):
        """Użytkownik zakłada typ per dostawca — „Produkt Aspironix”."""
        assert typ_dokumentu(podziel_naglowek(KARTA)[0],
                             {"produkt-aspironix": "Produkt Aspironix"}) == "produkt-aspironix"

    def test_jawny_typ_z_naglowka_wygrywa(self):
        naglowek = dict(podziel_naglowek(KARTA)[0], typ="karta-produktu")
        assert typ_dokumentu(naglowek, {"karta-produktu": "Karta produktu",
                                        "produkt-aspironix": "Produkt Aspironix"}) == "karta-produktu"

    def test_brak_pasujacego_typu_zostawia_decyzje_modelowi(self):
        assert typ_dokumentu(podziel_naglowek(KARTA)[0], {"umowa": "Umowa"}) is None


class TestPrzygotowania:
    @pytest.fixture
    def katalog(self, tmp_path):
        plik = tmp_path / "actisorb-plus-25.md"
        plik.write_text(KARTA, encoding="utf-8")
        return str(plik)

    def test_powstaje_pdf_obok_zrodla(self, katalog):
        wynik = przygotuj(katalog)
        assert os.path.exists(wynik["sciezka_pdf"])
        assert os.path.exists(wynik["sciezka_md"])

    def test_wspolny_rdzen_nazwy(self, katalog):
        """Zmiana nazwy i usuwanie pliku szukają pochodnych po TYM SAMYM rdzeniu."""
        wynik = przygotuj(katalog)
        rdzen = lambda p: os.path.splitext(os.path.basename(p))[0]
        assert rdzen(wynik["sciezka_md"]) == rdzen(wynik["sciezka_pdf"])

    def test_nazwa_dokumentu_z_produktu_nie_ze_sluga(self, katalog):
        wynik = przygotuj(katalog)
        assert wynik["nazwa"].startswith("ACTISORB PLUS 25")
        assert wynik["nazwa"].endswith(".pdf")
        assert wynik["nazwa_pierwotna"] == "actisorb-plus-25.md"

    def test_pdf_jest_czytelny_maszynowo(self, katalog):
        """Do parsowania idzie ten PDF — musi mieć warstwę tekstową, nie sam obraz."""
        fitz = pytest.importorskip("fitz")
        wynik = przygotuj(katalog)
        with fitz.open(wynik["sciezka_pdf"]) as d:
            tekst = " ".join(s.get_text() for s in d)
        assert "Opatrunek wykazuje skuteczne działanie" in tekst
        assert "oczyszcza rany zainfekowane" in tekst

    def test_pdf_niesie_date_waznosci_i_zastrzezenie(self, katalog):
        fitz = pytest.importorskip("fitz")
        wynik = przygotuj(katalog)
        with fitz.open(wynik["sciezka_pdf"]) as d:
            tekst = " ".join(s.get_text() for s in d)
        assert "Stan na 21 sierpnia 2026" in tekst
        assert "Nie jest dokumentem organizacji" in tekst
        assert "aspironix.pl" in tekst

    def test_blok_zastrzezenia_tylko_dla_materialu_zewnetrznego(self, tmp_path):
        """Plik bez adresu źródłowego to nie materiał dostawcy — nie strasz zastrzeżeniem."""
        fitz = pytest.importorskip("fitz")
        cel = str(tmp_path / "wlasny.pdf")
        zbuduj_pdf({"nazwa": "Notatka własna", "pobrano": "2026-08-21"}, "## Treść\n\nabc", cel)
        with fitz.open(cel) as d:
            tekst = " ".join(s.get_text() for s in d)
        assert "Stan na 21 sierpnia 2026" in tekst
        assert "Nie jest dokumentem organizacji" not in tekst


class TestDaty:
    def test_data_slownie_po_polsku(self):
        assert data_slownie("2026-08-21") == "21 sierpnia 2026"

    def test_zla_data_nie_wywraca(self):
        assert data_slownie("kiedyś") is None
