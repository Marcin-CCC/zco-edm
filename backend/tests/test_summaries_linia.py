"""Testy kontroli obowiązkowej linii „Inne określenia" w streszczeniach.

Uruchom: pytest backend/tests/test_summaries_linia.py -v

Ta linia to jedyne miejsce, w którym streszczenie mówi językiem pracownika
(„delegacja" zamiast „podróż służbowa"). Jej brak wycisza dokument dla wszystkich
pytań zadanych potocznie — i przez to przeszedł niezauważony w 20 z 188 dokumentów.
Rozpoznanie musi być odporne na drobne warianty zapisu, ale nie może uznawać za
tę linię czegoś, co nią nie jest.
"""
import pytest

from app.summaries import ma_linie_zamiennikow

PELNY = (
    "OPIS: Regulamin zakładowego funduszu świadczeń socjalnych.\n"
    "Inne określenia: ZFŚS, fundusz socjalny, socjal, wczasy pod gruszą\n"
    "Pytania: Kto może korzystać z funduszu?"
)


class TestRozpoznawanieLinii:
    def test_pelny_opis(self):
        assert ma_linie_zamiennikow(PELNY) is True

    @pytest.mark.parametrize("wariant", [
        "Inne określenia: delegacja, wyjazd",
        "inne określenia: delegacja",
        "INNE OKREŚLENIA: delegacja",
        "   Inne określenia: delegacja",        # wcięcie
        "Inne określenia - delegacja, wyjazd",  # myślnik zamiast dwukropka
    ])
    def test_warianty_zapisu(self, wariant):
        assert ma_linie_zamiennikow(f"OPIS: cokolwiek\n{wariant}\nPytania: x") is True

    @pytest.mark.parametrize("opis", [
        "OPIS: Regulamin.\nPytania: Kto może korzystać?",       # brak linii
        "",
        "OPIS: dokument o innych określeniach prawnych",        # fraza w środku zdania
    ])
    def test_brak_linii(self, opis):
        assert ma_linie_zamiennikow(opis) is False

    def test_none_nie_wywala(self):
        assert ma_linie_zamiennikow(None) is False

    def test_fraza_musi_zaczynac_linie(self):
        """„inne określenia" w środku zdania to nie jest ta linia — inaczej
        naprawa pomijałaby dokumenty, które faktycznie jej nie mają."""
        opis = "OPIS: Dokument opisuje inne określenia stosowane w szpitalu.\nPytania: x"
        assert ma_linie_zamiennikow(opis) is False
