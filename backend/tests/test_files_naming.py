"""Testy budowania nazw plików z rozpoznanych pól dokumentu.

Uruchom: pytest backend/tests/test_files_naming.py -v

Największe ryzyko tej funkcji to nazwa zbudowana z dziurą („zarzadzenie-nr--2009")
albo taka, która sama tworzy kolizję — czyli dokładnie ten problem, który ma leczyć.
Stąd nacisk na braki pól i na numerowanie przy powtórzeniach.
"""
import pytest

from app.files.naming import build_filename, missing_placeholders, unique_filename
from app.text_utils import slugify, strip_diacritics

WZORZEC = "{typ}-nr-{numer}-{data}"
POLA = {"numer": "1/2009", "data": "2009-01-09"}


class TestSlugify:
    @pytest.mark.parametrize("wejscie,oczekiwane", [
        ("Zarządzenie", "zarzadzenie"),
        ("Żłobek Miejski", "zlobek-miejski"),
        ("1/2009", "1-2009"),
        ("2009-01-09", "2009-01-09"),          # data ISO przechodzi bez zmian
        ('a\\b/c:d*e?f"g<h>i|j', "a-b-c-d-e-f-g-h-i-j"),  # znaki zakazane w nazwie pliku
        ("   ---  ", ""),
    ])
    def test_sprowadza_do_bezpiecznych_znakow(self, wejscie, oczekiwane):
        assert slugify(wejscie) == oczekiwane

    def test_przycina_do_dlugosci_bez_wiszacego_myslnika(self):
        assert slugify("aaa bbb ccc", max_length=8) == "aaa-bbb"

    def test_strip_diacritics_zostawia_reszte(self):
        assert strip_diacritics("Zażółć GĘŚLĄ jaźń") == "zazolc gesla jazn"


class TestBuildFilename:
    def test_zmierzony_przypadek_zarzadzenia(self):
        nazwa, braki = build_filename(WZORZEC, "zarzadzenie", POLA, "pdf")
        assert nazwa == "zarzadzenie-nr-1-2009-2009-01-09.pdf"
        assert braki == []

    def test_rozszerzenie_bierzemy_z_oryginalu(self):
        nazwa, _ = build_filename(WZORZEC, "zarzadzenie", POLA, ".DOCX")
        assert nazwa.endswith(".docx")

    def test_brak_pola_wstrzymuje_nazwe(self):
        """Słaby OCR gubi numer. Lepiej pominąć plik i powiedzieć czego brakuje,
        niż zbudować „zarzadzenie-nr--2009-01-09"."""
        nazwa, braki = build_filename(WZORZEC, "zarzadzenie", {"data": "2009-01-09"}, "pdf")
        assert nazwa is None
        assert braki == ["numer"]

    def test_puste_pole_liczy_sie_jak_brak(self):
        nazwa, braki = build_filename(WZORZEC, "zarzadzenie", {"numer": "  ", "data": "2009-01-09"}, "pdf")
        assert nazwa is None and braki == ["numer"]

    def test_kilka_brakow_naraz(self):
        assert missing_placeholders(WZORZEC, "zarzadzenie", {}) == ["numer", "data"]

    def test_brak_wzorca_to_brak_nazwy(self):
        nazwa, braki = build_filename("", "zarzadzenie", POLA, "pdf")
        assert nazwa is None and braki == ["wzorzec"]

    def test_wzorzec_bez_pol_tez_dziala(self):
        """Typ dokumentu wystarczy — przyda się kategoriom bez pól."""
        nazwa, braki = build_filename("{typ}", "instrukcja", {}, "odt")
        assert (nazwa, braki) == ("instrukcja.odt", [])

    def test_pole_wielowartosciowe_sklejamy(self):
        nazwa, _ = build_filename("{typ}-{osoby}", "protokol", {"osoby": ["Jan Kowalski", "Anna Nowak"]}, "pdf")
        assert nazwa == "protokol-jan-kowalski-anna-nowak.pdf"

    def test_nazwa_nie_przekracza_limitu(self):
        nazwa, _ = build_filename("{typ}-{opis}", "umowa", {"opis": "x" * 300}, "pdf")
        assert len(nazwa) <= 125


class TestUniqueFilename:
    def test_wolna_nazwa_zostaje(self):
        assert unique_filename("a.pdf", set()) == "a.pdf"

    def test_kolizja_dostaje_numer_kolejny(self):
        assert unique_filename("a.pdf", {"a.pdf"}) == "a-2.pdf"
        assert unique_filename("a.pdf", {"a.pdf", "a-2.pdf"}) == "a-3.pdf"

    def test_numer_przed_rozszerzeniem_a_nie_po(self):
        """`a.pdf-2` przestałoby być PDF-em dla systemu i dla przeglądarki."""
        assert unique_filename("a.pdf", {"a.pdf"}).endswith(".pdf")

    def test_nazwa_bez_rozszerzenia(self):
        assert unique_filename("raport", {"raport"}) == "raport-2"


class TestPropozycjeNazw:
    """Podgląd dla partii plików — tu mieszka logika, która najłatwiej zawiedzie:
    kolizje w obrębie jednej partii i pliki, dla których nazwy zbudować się nie da."""

    @pytest.fixture
    def db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.database import Base
        from app.models import DocTypeSchema

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(DocTypeSchema(
                slug="zarzadzenie", name="Zarządzenie", fields=[],
                name_pattern="{typ}-nr-{numer}-{data}", active=True,
            ))
            session.add(DocTypeSchema(
                slug="notatka", name="Notatka", fields=[], name_pattern=None, active=True,
            ))
            session.commit()
            yield session

    def plik(self, db, id_, nazwa, doc_type=None, pola=None):
        from app.models import File as FileModel
        f = FileModel(id=id_, filename=nazwa, file_path=f"/data/{id_}/{nazwa}",
                      uploaded_by=1, metadata_={"doc_type": doc_type, "doc_fields": pola or {}})
        db.add(f)
        db.commit()
        return f

    def test_buduje_nazwe_z_pol(self, db):
        from app.files.router import _propozycje_nazw
        f = self.plik(db, 1, "1.pdf", "zarzadzenie", {"numer": "1/2009", "data": "2009-01-09"})
        [poz] = _propozycje_nazw([f], db)
        assert poz["proponowana"] == "zarzadzenie-nr-1-2009-2009-01-09.pdf"
        assert poz["problem"] is None

    def test_dwa_takie_same_dostaja_rozne_nazwy(self, db):
        """Sedno: funkcja lecząca powtórzone nazwy nie może ich tworzyć."""
        from app.files.router import _propozycje_nazw
        pola = {"numer": "1/2009", "data": "2009-01-09"}
        pliki = [self.plik(db, 1, "1.pdf", "zarzadzenie", pola),
                 self.plik(db, 2, "kopia.pdf", "zarzadzenie", pola)]
        nazwy = [p["proponowana"] for p in _propozycje_nazw(pliki, db)]
        assert nazwy == ["zarzadzenie-nr-1-2009-2009-01-09.pdf",
                         "zarzadzenie-nr-1-2009-2009-01-09-2.pdf"]

    def test_kolizja_z_nazwa_juz_w_bazie(self, db):
        from app.files.router import _propozycje_nazw
        self.plik(db, 9, "zarzadzenie-nr-1-2009-2009-01-09.pdf")
        f = self.plik(db, 1, "1.pdf", "zarzadzenie", {"numer": "1/2009", "data": "2009-01-09"})
        [poz] = _propozycje_nazw([f], db)
        assert poz["proponowana"] == "zarzadzenie-nr-1-2009-2009-01-09-2.pdf"

    def test_brak_kategorii(self, db):
        from app.files.router import _propozycje_nazw
        f = self.plik(db, 1, "skan.pdf", None)
        [poz] = _propozycje_nazw([f], db)
        assert poz["proponowana"] is None
        assert "kategorii" in poz["problem"]

    def test_kategoria_bez_wzorca(self, db):
        from app.files.router import _propozycje_nazw
        f = self.plik(db, 1, "skan.pdf", "notatka")
        [poz] = _propozycje_nazw([f], db)
        assert poz["proponowana"] is None and "wzorca" in poz["problem"]

    def test_brak_pola_mowi_ktorego(self, db):
        """Słaby OCR gubi numer — użytkownik ma dostać powód, żeby wpisać nazwę ręcznie."""
        from app.files.router import _propozycje_nazw
        f = self.plik(db, 1, "1.pdf", "zarzadzenie", {"data": "2009-01-09"})
        [poz] = _propozycje_nazw([f], db)
        assert poz["proponowana"] is None
        assert poz["problem"] == "brak pól: numer"

