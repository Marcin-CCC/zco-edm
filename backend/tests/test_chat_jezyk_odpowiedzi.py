"""Testy języka, w którym model ma napisać odpowiedź (krok 7 wielojęzyczności).

Uruchom: pytest backend/tests/test_chat_jezyk_odpowiedzi.py -v

Instrukcja jest WARUNKOWA. Dla osoby pracującej po polsku doklejenie jej to sama
strata: kilkadziesiąt tokenów promptu na powiedzenie modelowi, żeby robił to, co
i tak robi, plus ryzyko, że zacznie tłumaczyć cytowane wartości z dokumentów.

Zastrzeżenie o dokumentach musi w niej być. Kontekst jest w innym języku niż
odpowiedź i model bez uprzedzenia bierze to za pomyłkę — albo przechodzi na język
dokumentów, albo tłumaczy numery i nazwy własne. Nazwa pliku przetłumaczona na
angielski przestaje pasować do listy źródeł pod odpowiedzią.
"""
import pytest

from app.chat.answer_language import NAZWY_JEZYKOW, language_instruction
from app.locales import BASE_LOCALE, SUPPORTED_LOCALES


class TestKiedyInstrukcjaWchodzi:
    @pytest.mark.parametrize("kod", [None, "", "pl", "PL", "pl-PL"])
    def test_po_polsku_bez_instrukcji(self, kod):
        """Język bazowy = model i tak odpowiada po polsku. Prompt zostaje krótszy."""
        assert language_instruction(kod) == ""

    @pytest.mark.parametrize("kod", [k for k in SUPPORTED_LOCALES if k != BASE_LOCALE])
    def test_kazdy_obcy_jezyk_dostaje_instrukcje(self, kod):
        tekst = language_instruction(kod)
        assert tekst, f"brak instrukcji dla {kod}"
        assert NAZWY_JEZYKOW[kod] in tekst

    @pytest.mark.parametrize("kod", ["fr", "klingoński", "xx-YY"])
    def test_nieobslugiwany_kod_nie_daje_polecenia_z_none(self, kod):
        """Lepiej odpowiedź po polsku niż polecenie „odpowiadaj w języku None"."""
        assert language_instruction(kod) == ""

    def test_zapis_z_regionem_dziala(self):
        assert language_instruction("en-US") == language_instruction("en")


class TestTresciInstrukcji:
    @pytest.fixture
    def po_angielsku(self):
        return language_instruction("en")

    def test_mowi_o_innym_jezyku_dokumentow(self, po_angielsku):
        """Bez tego model traktuje różnicę języków jak pomyłkę."""
        assert "Kontekst jest w innym języku" in po_angielsku

    def test_nie_obiecuje_ze_dokumenty_sa_wylacznie_polskie(self, po_angielsku):
        """Zbiór NIE jest jednojęzyczny — materiały od dostawców bywają po angielsku."""
        assert "najczęściej polskim" in po_angielsku

    def test_zabrania_tlumaczenia_nazw_i_numerow(self, po_angielsku):
        """Przetłumaczona nazwa pliku nie pasuje do listy źródeł pod odpowiedzią,
        a przetłumaczony numer zarządzenia jest po prostu nieprawdziwy."""
        assert "NIE tłumacz" in po_angielsku
        for czego in ("nazw plików", "numerów dokumentów", "wartości liczbowych"):
            assert czego in po_angielsku

    def test_obejmuje_takze_zdanie_o_braku_informacji(self, po_angielsku):
        """Odmowa też jest odpowiedzią — po angielsku ma być po angielsku."""
        assert "braku informacji" in po_angielsku

    def test_znaczniki_cytowan_zostaja_bez_zmian(self, po_angielsku):
        """Znaczniki są neutralne językowo (krok 1); tłumaczenie ich zerwałoby
        wiązanie odpowiedzi ze źródłami."""
        assert "Znaczniki cytowań przepisz bez zmian" in po_angielsku

    def test_kazdy_obslugiwany_jezyk_ma_nazwe(self):
        """Brak nazwy = instrukcja by nie powstała, a język wyglądałby na działający."""
        brakujace = [k for k in SUPPORTED_LOCALES if k != BASE_LOCALE and k not in NAZWY_JEZYKOW]
        assert not brakujace, f"brak nazwy dla: {brakujace}"
