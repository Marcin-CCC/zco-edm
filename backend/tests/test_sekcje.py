"""Testy podziału dokumentu na sekcje.

Uruchom: pytest backend/tests/test_sekcje.py -v

Podział decyduje o tym, czy sekcję da się później ZAADRESOWAĆ w wyszukiwaniu.
Najmniejszą jednostką, którą umiemy wskazać, jest strona (`metadata.page`), więc
sekcja urwana w połowie strony byłaby bezużyteczna — stąd nacisk na granice.
"""
import pytest

from app.sekcje import MIN_ZNAKOW_SEKCJI, podziel_na_sekcje


def podstaw(monkeypatch, fragmenty):
    # Podstawiamy nazwę W MODULE `sekcje`, bo importuje ją przy starcie (`from ... import`),
    # więc podmiana w `qdrant_client` nie miałaby już żadnego wpływu.
    monkeypatch.setattr("app.sekcje.get_chunks_by_file_id", lambda fid: fragmenty)


def strona(nr, znakow, litera="a"):
    return (nr, 1, litera * znakow)


class TestPodzialu:
    def test_krotki_dokument_to_jedna_sekcja(self, monkeypatch):
        podstaw(monkeypatch, [strona(1, 300), strona(2, 300)])
        sekcje = podziel_na_sekcje(1, budzet=12000)
        assert len(sekcje) == 1
        assert (sekcje[0]["strona_od"], sekcje[0]["strona_do"]) == (1, 2)

    def test_dzieli_po_wyczerpaniu_budzetu(self, monkeypatch):
        podstaw(monkeypatch, [strona(i, 400) for i in range(1, 11)])
        sekcje = podziel_na_sekcje(1, budzet=1000)
        # 400+400 = 800 mieści się, trzecia strona przekracza → nowa sekcja
        assert [(s["strona_od"], s["strona_do"]) for s in sekcje] == [
            (1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]

    def test_nigdy_nie_dzieli_strony(self, monkeypatch):
        """Strona dłuższa niż budżet idzie w całości — połowy strony i tak nie
        umielibyśmy wskazać w wyszukiwaniu."""
        podstaw(monkeypatch, [strona(1, 500), strona(2, 9000), strona(3, 500)])
        sekcje = podziel_na_sekcje(1, budzet=1000)
        assert all(s["strona_od"] <= s["strona_do"] for s in sekcje)
        duza = [s for s in sekcje if s["strona_od"] == 2]
        assert len(duza) == 1 and len(duza[0]["tekst"]) >= 9000

    def test_skleja_fragmenty_tej_samej_strony(self, monkeypatch):
        podstaw(monkeypatch, [(1, 1, "aaa"), (1, 5, "bbb"), (2, 1, "ccc")])
        sekcje = podziel_na_sekcje(1, budzet=12000)
        assert "aaa" in sekcje[0]["tekst"] and "bbb" in sekcje[0]["tekst"]
        assert sekcje[0]["strona_do"] == 2

    def test_krotki_ogon_dokleja_sie_do_poprzedniej(self, monkeypatch):
        """Resztka na kilkadziesiąt znaków nie jest tematem — opisywanie jej osobno
        to zmarnowane wywołanie modelu i śmieciowy cel wyszukiwania."""
        podstaw(monkeypatch, [strona(1, 900), strona(2, 900), strona(3, 50)])
        sekcje = podziel_na_sekcje(1, budzet=1000)
        assert sekcje[-1]["strona_do"] == 3
        assert len(sekcje[-1]["tekst"]) > MIN_ZNAKOW_SEKCJI

    def test_pomija_puste_fragmenty(self, monkeypatch):
        podstaw(monkeypatch, [(1, 1, "   "), (2, 1, "treść")])
        sekcje = podziel_na_sekcje(1)
        assert len(sekcje) == 1 and sekcje[0]["strona_od"] == 2

    @pytest.mark.parametrize("fragmenty", [[], [(1, 1, "")], [(1, 1, "   ")]])
    def test_brak_tresci_to_brak_sekcji(self, monkeypatch, fragmenty):
        podstaw(monkeypatch, fragmenty)
        assert podziel_na_sekcje(1) == []

    def test_zakresy_stron_sa_ciagle(self, monkeypatch):
        """Żadna strona nie może wypaść między sekcjami ani trafić do dwóch naraz."""
        podstaw(monkeypatch, [strona(i, 400) for i in range(1, 21)])
        sekcje = podziel_na_sekcje(1, budzet=1000)
        pokryte = []
        for s in sekcje:
            pokryte += list(range(s["strona_od"], s["strona_do"] + 1))
        assert pokryte == list(range(1, 21))
