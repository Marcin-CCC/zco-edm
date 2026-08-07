"""Testy planowania zakresu wyszukiwania (cztery ścieżki retrievalu).

Uruchom: pytest backend/tests/test_chat_zakres.py -v

Ten moduł powstał z wydzielenia kodu z `chat/router.py`, więc testy pilnują przede
wszystkim, żeby wydzielenie NICZEGO nie zmieniło: który filtr powstaje na której
ścieżce, kiedy próg trafności ma być wyłączony i czy filtr uprawnień nigdy nie
gubi się po drodze. Zależności zewnętrzne (Qdrant, model osadzeń) podstawiamy.
"""
import asyncio

import pytest

from app.chat.zakres import PlanZakresu, zaplanuj_zakres

RBAC = {"key": "metadata.folder_id", "match": {"any": [4, 7]}}


@pytest.fixture
def uslugi(monkeypatch):
    """Podstawione usługi + rejestr tego, co zostało zawołane."""
    slad = {"osadzenia": 0, "dobory": 0, "filtr_wyszukiwania": None}

    async def osadz(_):
        slad["osadzenia"] += 1
        return [0.1, 0.2, 0.3]

    def szukaj(w, filtr=None, limit=15):
        slad["filtr_wyszukiwania"] = filtr
        return [{"score": 0.61, "file_id": 5, "filename": "Regulamin.pdf",
                 "page": 1, "content": "treść regulaminu o urlopach"}]

    async def wskaz(pytanie, filtr, foldery, wektor_pytania=None):
        return [], False, "bez zmian"

    async def dobierz(pytanie, w_kontekscie, filtr, wektoryzuj, szukajf):
        slad["dobory"] += 1
        return []

    monkeypatch.setattr("app.summaries.wektor", osadz)
    monkeypatch.setattr("app.qdrant_client.search_chunks_full", szukaj)
    monkeypatch.setattr("app.qdrant_client.count_points", lambda: 3129)
    monkeypatch.setattr("app.qdrant_client.count_chunks_with_text", lambda t: 5)
    monkeypatch.setattr("app.chat.streszczenia.wskaz_dokumenty", wskaz)
    monkeypatch.setattr("app.chat.dobor.dobierz_fragmenty", dobierz)
    monkeypatch.setattr("app.chat.lexical.terminy_selektywne",
                        lambda *a, **k: [])
    return slad


def plan(**kwargs) -> PlanZakresu:
    baza = dict(pytanie="jakie są zasady urlopu?", search_query="jakie są zasady urlopu?",
                file_ids=None, folder_filter_enabled=True, allowed_folder_ids=[4, 7],
                znane_rdzenie=set())
    baza.update(kwargs)
    return asyncio.run(zaplanuj_zakres(**baza))


class TestScopedToFiles:
    """Próg trafności w n8n wyłączamy dokładnie w trzech sytuacjach."""

    @pytest.mark.parametrize("pola,oczekiwane", [
        ({}, False),
        ({"wskazane_pliki": [1, 2]}, True),
        ({"terminy": ["dynars"]}, True),
        ({"bez_progu": True}, True),
        ({"wskazane_streszczeniem": [9]}, False),   # samo UZUPEŁNIENIE progu nie zdejmuje
    ])
    def test_warunki(self, pola, oczekiwane):
        assert PlanZakresu(**pola).scoped_to_files is oczekiwane


class TestSciezkaZwykla:
    def test_filtr_to_same_uprawnienia(self, uslugi):
        p = plan()
        assert p.qdrant_filter == {"must": [RBAC]}
        assert p.warunki_rbac == [RBAC]
        assert p.scoped_to_files is False

    def test_bez_uprawnien_filtr_pusty(self, uslugi):
        p = plan(folder_filter_enabled=False, allowed_folder_ids=[])
        assert p.qdrant_filter is None
        assert p.warunki_rbac == []

    def test_prog_odsiewa_kontekst(self, uslugi):
        """Na ścieżce zwykłej do kontekstu wchodzi tylko to, co nad progiem."""
        p = plan()
        assert len(p.trafienia) == 1
        assert len(p.w_kontekscie) == 1        # 0,61 >= 0,50


class TestSciezkaWskazanePliki:
    def test_filtr_ma_pliki_i_uprawnienia(self, uslugi):
        p = plan(file_ids=[9, 3, 9])
        assert p.qdrant_filter == {"must": [
            RBAC, {"key": "metadata.file_id", "match": {"any": [3, 9]}}]}
        assert p.scoped_to_files is True

    def test_nie_ma_osadzania_ani_doboru(self, uslugi):
        """Zakres ustalił użytkownik — nie dokładamy mu niczego od siebie."""
        plan(file_ids=[9])
        assert uslugi["osadzenia"] == 0
        assert uslugi["dobory"] == 0


class TestSciezkaLeksykalna:
    def test_filtr_dostaje_should(self, monkeypatch, uslugi):
        monkeypatch.setattr("app.chat.lexical.terminy_selektywne",
                            lambda *a, **k: ["dynars", "jolant"])
        p = plan()
        assert p.terminy == ["dynars", "jolant"]
        assert p.qdrant_filter["must"][1] == {"should": [
            {"key": "content", "match": {"text": "dynars"}},
            {"key": "content", "match": {"text": "jolant"}}]}
        assert p.scoped_to_files is True

    def test_uprawnienia_bez_zawezenia_leksykalnego(self, monkeypatch, uslugi):
        """Dobór szuka po uprawnieniach, NIE po rzadkim słowie — zawężenie miało
        wskazać dokument, a nie ograniczać wybór strony w jego wnętrzu."""
        monkeypatch.setattr("app.chat.lexical.terminy_selektywne",
                            lambda *a, **k: ["dynars"])
        p = plan()
        assert p.warunki_rbac == [RBAC]

    def test_caly_wynik_wchodzi_do_kontekstu(self, monkeypatch, uslugi):
        """Przy zawężeniu próg jest wyłączony, więc kontekst = wszystkie trafienia."""
        monkeypatch.setattr("app.chat.lexical.terminy_selektywne",
                            lambda *a, **k: ["dynars"])
        monkeypatch.setattr("app.qdrant_client.search_chunks_full",
                            lambda w, f=None, limit=15: [
                                {"score": 0.61, "file_id": 5, "filename": "a.pdf",
                                 "page": 1, "content": "x"},
                                {"score": 0.31, "file_id": 5, "filename": "a.pdf",
                                 "page": 2, "content": "y"}])
        p = plan()
        assert len(p.w_kontekscie) == 2

    def test_bez_pytania_o_streszczenia(self, monkeypatch, uslugi):
        async def nie_wolno(*a, **k):
            raise AssertionError("streszczenia nie powinny być pytane przy zawężeniu")
        monkeypatch.setattr("app.chat.lexical.terminy_selektywne",
                            lambda *a, **k: ["dynars"])
        monkeypatch.setattr("app.chat.streszczenia.wskaz_dokumenty", nie_wolno)
        plan()


class TestSciezkaStreszczen:
    def test_zawezenie_zdejmuje_prog(self, monkeypatch, uslugi):
        async def wskaz(pytanie, filtr, foldery, wektor_pytania=None):
            return [11, 12], True, "zawężam do [11, 12]"
        monkeypatch.setattr("app.chat.streszczenia.wskaz_dokumenty", wskaz)
        p = plan()
        assert p.wskazane_streszczeniem == [11, 12]
        assert p.scoped_to_files is True
        assert p.qdrant_filter["must"][1] == {
            "key": "metadata.file_id", "match": {"any": [11, 12]}}

    def test_uzupelnienie_zostawia_prog(self, monkeypatch, uslugi):
        async def wskaz(pytanie, filtr, foldery, wektor_pytania=None):
            return [11], False, "uzupełniam o [11]"
        monkeypatch.setattr("app.chat.streszczenia.wskaz_dokumenty", wskaz)
        assert plan().scoped_to_files is False


class TestOdpornosc:
    def test_awaria_osadzenia_nie_przerywa(self, monkeypatch, uslugi):
        async def pada(_):
            raise RuntimeError("Ollama nie odpowiada")
        monkeypatch.setattr("app.summaries.wektor", pada)
        p = plan()
        assert p.qdrant_filter == {"must": [RBAC]}   # plan powstaje mimo awarii
        assert p.dobrane == []

    def test_awaria_qdranta_nie_przerywa(self, monkeypatch, uslugi):
        def pada(*a, **k):
            raise RuntimeError("Qdrant nieosiągalny")
        monkeypatch.setattr("app.qdrant_client.search_chunks_full", pada)
        p = plan()
        assert p.dobrane == []
        assert p.trafienia == []
