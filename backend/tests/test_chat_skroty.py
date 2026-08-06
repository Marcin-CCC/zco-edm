"""Testy wykrywania skrótów nieobecnych w dokumentach.

Uruchom: pytest backend/tests/test_chat_skroty.py -v

Fałszywe ostrzeżenie jest tu groźniejsze niż brak ostrzeżenia: kazałoby modelowi
milczeć o pojęciu, które W DOKUMENTACH JEST. Stąd nacisk na przypadki graniczne.
"""
import pytest

from app.chat.skroty import nieznane_skroty, skroty_z_pytania, uwaga_o_skrotach


class TestWykrywanieSkrotow:
    @pytest.mark.parametrize("pytanie,oczekiwane", [
        ("czy mogę przystąpić do PPK w ZCO?", ["PPK", "ZCO"]),
        ("co to jest ZFŚS", ["ZFŚS"]),
        ("jak zgłosić L4", ["L4"]),
        ("RODO a dokumentacja medyczna", ["RODO"]),
        ("jak rozliczyć delegację", []),
        ("", []),
    ])
    def test_wyciaga_skroty(self, pytanie, oczekiwane):
        assert skroty_z_pytania(pytanie) == oczekiwane

    def test_pomija_wersaliki_bez_znaczenia(self):
        assert skroty_z_pytania("CZY MOGE przystapic do PPK") == ["PPK"]

    def test_bez_powtorzen(self):
        assert skroty_z_pytania("PPK, a potem znowu PPK i PPK") == ["PPK"]


class TestNieznaneSkroty:
    def test_zglasza_tylko_nieobecne(self):
        baza = {"ppk": 40, "zco": 0}
        assert nieznane_skroty("czy mogę przystąpić do PPK w ZCO?", baza.get) == ["ZCO"]

    def test_nic_gdy_wszystko_znane(self):
        assert nieznane_skroty("co z PPK i RODO", lambda t: 5) == []

    def test_awaria_liczenia_nie_ostrzega(self):
        """None = nie wiemy, czy skrót jest w bazie. Lepiej nie ostrzegać fałszywie."""
        assert nieznane_skroty("co to jest ZCO", lambda t: None) == []

    def test_limit_liczby_skrotow(self):
        wynik = nieznane_skroty("ZCO ABC DEF GHI JKL", lambda t: 0)
        assert len(wynik) == 3


class TestTrescOstrzezenia:
    def test_puste_gdy_brak_skrotow(self):
        assert uwaga_o_skrotach([]) == ""

    def test_zawiera_oba_poleceniaZ(self):
        """Pomiar: sam zakaz zgadywania daje pełną odmowę 5/5. Musi być też polecenie
        odpowiedzi na resztę pytania."""
        u = uwaga_o_skrotach(["ZCO"])
        assert "ZCO" in u
        assert "Nie zgaduj" in u
        assert "pozostałą" in u

    def test_odmiana_dla_wielu(self):
        u = uwaga_o_skrotach(["ZCO", "ABC"])
        assert "tych skrótów" in u and "ZCO" in u and "ABC" in u
