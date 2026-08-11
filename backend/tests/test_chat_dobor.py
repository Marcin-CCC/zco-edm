"""Testy doboru fragmentów z dokumentu-zwycięzcy.

Uruchom: pytest backend/tests/test_chat_dobor.py -v

Największym ryzykiem NIE jest brak doboru, tylko dobór zbędny: doklejone fragmenty
omijają próg trafności, więc odpalony bez potrzeby dosypuje modelowi treści, które
nie dotyczą pytania. Stąd większość testów sprawdza, kiedy mechanizm ma MILCZEĆ.
"""
import asyncio

import pytest

from app.chat.dobor import (
    dobierz_fragmenty,
    dokument_zwyciezca,
    niepokryta_reszta,
    plan_doboru,
    scal_dobrane,
    slowa_tresciowe,
    zapytanie_uzupelniajace,
)


def traf(score, fid, filename, content, page=1):
    return {"score": score, "file_id": fid, "filename": filename,
            "content": content, "page": page}


# Odwzorowanie zmierzonego przypadku: sześć fragmentów o „wczasach pod gruszą"
# nad progiem, w żadnym ani słowa o wieku.
GRUSZA = [
    traf(0.60, 203, "Zarządzenie i Regulamin ZFŚS.pdf",
         "dofinansowanie wypoczynku wczasy pod gruszą dla osób uprawnionych", 8),
    traf(0.56, 203, "Zarządzenie i Regulamin ZFŚS.pdf",
         "zwrot świadczenia wczasy pod gruszą na konto Funduszu", 9),
    traf(0.55, 203, "Zarządzenie i Regulamin ZFŚS.pdf",
         "wniosek o dofinansowanie wypoczynku dzieci pracownika", 10),
    traf(0.52, 311, "Regulamin ZFŚS 2026.pdf",
         "wczasy pod gruszą przysługują raz w roku kalendarzowym", 7),
]


class TestSlowaTresciowe:
    @pytest.mark.parametrize("pytanie,oczekiwane", [
        ("w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?",
         ["wieku", "dzieci", "wczasow", "grusza"]),
        ("ile wynosi dieta", ["dieta"]),
        ("", []),
    ])
    def test_zostaja_tylko_slowa_tematu(self, pytanie, oczekiwane):
        assert slowa_tresciowe(pytanie) == oczekiwane

    def test_bez_powtorzen(self):
        assert slowa_tresciowe("urlop i jeszcze raz urlop") == ["urlop", "jeszcze"]

    def test_pisownia_bez_ogonkow_daje_to_samo(self):
        assert slowa_tresciowe("wczasów pod gruszą") == slowa_tresciowe("wczasow pod grusza")


class TestNiepokrytaReszta:
    def test_wskazuje_brakujace_pojecie(self):
        reszta = niepokryta_reszta(
            "w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?",
            [t["content"] for t in GRUSZA],
        )
        assert reszta == ["wieku"]

    def test_nic_gdy_kontekst_pokrywa_pytanie(self):
        assert niepokryta_reszta("wczasy pod gruszą", [t["content"] for t in GRUSZA]) == []

    def test_odmiana_nie_myli(self):
        """„dzieci" w pytaniu, „dziecka" w dokumencie — to samo pojęcie."""
        assert niepokryta_reszta("dzieci", ["wypoczynek dziecka pracownika"]) == []
        assert niepokryta_reszta("wczasów", ["wczasy pod gruszą"]) == []


class TestDokumentZwyciezca:
    def test_wygrywa_suma_trafnosci(self):
        fid, nazwa, udzial = dokument_zwyciezca(GRUSZA)
        assert fid == 203
        assert nazwa == "Zarządzenie i Regulamin ZFŚS.pdf"
        assert udzial == pytest.approx((0.60 + 0.56 + 0.55) / 2.23, abs=0.01)

    def test_brak_trafien(self):
        assert dokument_zwyciezca([]) is None

    def test_pomija_fragmenty_bez_pliku(self):
        assert dokument_zwyciezca([traf(0.9, None, "x", "y")]) is None


class TestZapytanieUzupelniajace:
    def test_dokleja_tytul_bez_rozszerzenia(self):
        assert (zapytanie_uzupelniajace(["wieku"], "Regulamin ZFŚS 2026.pdf")
                == "wieku Regulamin ZFŚS 2026")

    def test_radzi_sobie_z_docx(self):
        assert zapytanie_uzupelniajace(["kto"], "wniosek.DOCX") == "kto wniosek"


class TestPlanDoboru:
    def test_zmierzony_przypadek(self):
        zapytanie, fid = plan_doboru(
            "w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?", GRUSZA)
        assert fid == 203
        assert zapytanie == "wieku Zarządzenie i Regulamin ZFŚS"

    def test_pusty_kontekst_to_poprawna_odmowa(self):
        """Nic nie weszło do kontekstu → nie ratujemy odpowiedzi, której nie ma."""
        assert plan_doboru("w jakim wieku dzieci", []) is None

    def test_dziala_gdy_prog_wylaczony(self):
        """Ścieżka `terminy`/streszczeń: próg w n8n jest wyłączony, więc do kontekstu
        wchodzą też fragmenty poniżej 0,50. Zmierzone na żywym zapytaniu — to WŁAŚNIE
        tą ścieżką idzie pytanie o wczasy pod gruszą, a pierwsza wersja modułu jej
        nie obsługiwała."""
        slabe = GRUSZA + [
            traf(0.46, 512, "Warunki ubezpieczenia.pdf", "świadczenie dla dziecka", 6),
            traf(0.44, 512, "Warunki ubezpieczenia.pdf", "osierocenie dziecka", 5),
        ]
        zapytanie, fid = plan_doboru(
            "w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?", slabe)
        assert fid == 203
        assert zapytanie == "wieku Zarządzenie i Regulamin ZFŚS"

    def test_brak_luki_to_brak_doboru(self):
        assert plan_doboru("wczasy pod gruszą", GRUSZA) is None

    def test_za_duzo_niepokrytych_slow(self):
        """Kilka nieznanych pojęć naraz = chybione wyszukiwanie, nie luka w rozumowaniu."""
        assert plan_doboru("kara ewakuacja jednorożca stajnia", GRUSZA) is None

    def test_rozstrzelone_trafienia(self):
        rozne = [traf(0.60, i, f"plik{i}.pdf", "treść ogólna", 1) for i in range(1, 8)]
        assert plan_doboru("w jakim wieku dzieci", rozne) is None


class TestScalDobrane:
    def test_odsiewa_strony_juz_w_kontekscie(self):
        dobrane = [traf(0.5, 203, "z.pdf", "a", 8), traf(0.5, 203, "z.pdf", "b", 4)]
        wynik = scal_dobrane(dobrane, GRUSZA)
        assert [d["page"] for d in wynik] == [4]

    def test_limit_liczby(self):
        dobrane = [traf(0.5, 203, "z.pdf", "x", p) for p in range(20, 30)]
        assert len(scal_dobrane(dobrane, [])) == 3


class TestDobierzFragmenty:
    """Projekt nie ma pytest-asyncio, więc pętlę odpalamy wprost — jeden nowy
    moduł nie jest wart nowej zależności w obrazie backendu."""

    def test_zwraca_fragmenty_i_zachowuje_filtr_rbac(self):
        uzyty_filtr = {}

        async def wektoryzuj(_):
            return [0.1, 0.2]

        def szukaj(w, filtr, limit):
            uzyty_filtr.update(filtr)
            return [traf(0.41, 203, "Zarządzenie i Regulamin ZFŚS.pdf",
                         "dzieci od 5 roku życia do 18 lat", 4)]

        rbac = {"must": [{"key": "metadata.folder_id", "match": {"any": [7]}}]}
        wynik = asyncio.run(dobierz_fragmenty(
            "w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?",
            GRUSZA, rbac, wektoryzuj, szukaj))

        assert [d["page"] for d in wynik] == [4]
        assert wynik[0]["text"] == "dzieci od 5 roku życia do 18 lat"
        # `file_id` MUSI jechać z fragmentem: nazwa pliku nie identyfikuje dokumentu,
        # więc bez tego pola cytowanie mogłoby wskazać inny plik o tej samej nazwie.
        assert wynik[0]["file_id"] == 203
        # filtr uprawnień musi przetrwać, a warunek na plik tylko się dokłada
        assert rbac["must"][0] in uzyty_filtr["must"]
        assert {"key": "metadata.file_id", "match": {"value": 203}} in uzyty_filtr["must"]
        # oryginalny filtr nie może zostać zmodyfikowany w miejscu
        assert len(rbac["must"]) == 1
        # i nic poza uprawnieniami + plikiem — zawężenie leksykalne z pytania
        # NIE MOŻE ograniczać wyboru strony wewnątrz dokumentu
        assert len(uzyty_filtr["must"]) == 2

    def test_awaria_osadzenia_nie_przerywa_czatu(self):
        async def wektoryzuj(_):
            raise RuntimeError("Ollama padł")

        wynik = asyncio.run(dobierz_fragmenty(
            "w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?",
            GRUSZA, None, wektoryzuj, lambda *a: []))
        assert wynik == []

    def test_bez_planu_nie_szuka_wcale(self):
        async def wektoryzuj(_):
            raise AssertionError("nie powinno dojść do osadzenia")

        wynik = asyncio.run(dobierz_fragmenty(
            "wczasy pod gruszą", GRUSZA, None, wektoryzuj, lambda *a: []))
        assert wynik == []

    def test_pomija_fragmenty_bez_tresci(self):
        async def wektoryzuj(_):
            return [0.1]

        def szukaj(w, filtr, limit):
            return [traf(0.4, 203, "z.pdf", "   ", 4)]

        wynik = asyncio.run(dobierz_fragmenty(
            "w jakim wieku dzieci mogą korzystać z wczasów pod gruszą?",
            GRUSZA, None, wektoryzuj, szukaj))
        assert wynik == []
