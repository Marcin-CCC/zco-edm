"""Testy rozpoznawania pytań definicyjnych.

Uruchom: pytest backend/tests/test_chat_definicje.py -v

Sedno tych testów to dwie granice: pytanie o POJĘCIE (historia szkodzi, odcinamy)
kontra pytanie o byt WSKAZANY W ROZMOWIE (historia jest niezbędna, zostawiamy).
"""
import pytest

from app.chat.definicje import pytanie_definicyjne


class TestOdcinamyHistorie:
    """Pytania o znaczenie konkretnego pojęcia — tu historia produkuje zmyślenia."""

    @pytest.mark.parametrize("pytanie", [
        "co to jest ZCO",
        "co to jest PPK?",
        "rozwiń skrót zco",
        "Rozwiń skrót PPK",
        "co oznacza skrót L4",
        "czym jest dodatek stażowy",
        "co to za dokument F-303-000-002",
        "definicja podróży służbowej",
        "znaczenie skrótu ZFŚS",
        "co kryje się pod skrótem RODO",
        "co znaczy wynaczynienie",
    ])
    def test_rozpoznane(self, pytanie):
        assert pytanie_definicyjne(pytanie) is True


class TestZostawiamyHistorie:
    """Pytania wskazujące na coś z rozmowy — bez historii traciłyby sens."""

    @pytest.mark.parametrize("pytanie", [
        "co to jest ten dokument",
        "co to za dokument",
        "co to znaczy",
        "czym jest ta procedura",       # „ta" wskazuje na poprzednią turę
        "co oznacza to dla mnie",
    ])
    def test_pominiete(self, pytanie):
        assert pytanie_definicyjne(pytanie) is False


class TestZwykłePytania:
    """Wszystko, co nie pyta o znaczenie pojęcia — reguła nie może ich dotykać."""

    @pytest.mark.parametrize("pytanie", [
        "jak rozliczyć delegację",
        "ile wynosi dodatek stażowy",
        "kto zatwierdził instrukcję opieki pielęgniarskiej",
        "wniosek o urlop opiekuńczy",
        "a inne wnioski",
        "pokaż zarządzenia z 2024",
        "",
        "   ",
    ])
    def test_nie_dotyczy(self, pytanie):
        assert pytanie_definicyjne(pytanie) is False


class TestOdpornoscNaZapis:
    """Użytkownik pisze bez polskich znaków, małymi literami, z literówkami spacji."""

    @pytest.mark.parametrize("pytanie", [
        "rozwin skrot zco",
        "ROZWIŃ SKRÓT ZCO",
        "  co to jest ppk  ",
        "czym sa pracownicze plany kapitalowe",
    ])
    def test_rozpoznane_mimo_zapisu(self, pytanie):
        assert pytanie_definicyjne(pytanie) is True
