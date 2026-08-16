"""Testy odczytu stanu serwera pod panele Dashboardu.

Uruchom: pytest backend/tests/test_system_status.py -v

Testujemy części, które mogą po cichu skłamać: parsowanie metryk vLLM (nazwa
metryki bywa opatrzona etykietą modelu), wybór katalogu do pomiaru dysku oraz
pamięć podręczną. Samych odczytów z `/proc` nie testujemy — poza Linuksem ich
nie ma, a ich zadaniem jest właśnie zwrócić ``None`` zamiast wybuchnąć.
"""
import os

import pytest

from app.dashboard import system_status as st


@pytest.fixture(autouse=True)
def czysty_cache():
    """Każdy test zaczyna z pustą pamięcią podręczną — inaczej jeden zatruwa drugi."""
    st.wyczysc_cache()
    yield
    st.wyczysc_cache()


class TestMetryka:
    def test_prosta_linia(self):
        assert st._metryka("vllm:num_requests_running 3.0", "vllm:num_requests_running") == 3.0

    def test_z_etykieta_modelu(self):
        tekst = 'vllm:num_requests_waiting{model_name="Qwen/Qwen3-VL-30B"} 2.0'
        assert st._metryka(tekst, "vllm:num_requests_waiting") == 2.0

    def test_nie_myli_metryk_o_wspolnym_przedrostku(self):
        # „..._running" i „..._running_total" różnią się jednym słowem; gdyby
        # dopasowanie szło po zawieraniu, panel pokazywałby licznik od startu
        # usługi zamiast bieżącej kolejki.
        tekst = "vllm:num_requests_running_total 999.0\nvllm:num_requests_running 1.0"
        assert st._metryka(tekst, "vllm:num_requests_running") == 1.0

    def test_brak_metryki(self):
        assert st._metryka("# HELP coś innego\nfoo 1.0", "vllm:num_requests_running") is None

    def test_linia_bez_wartosci(self):
        assert st._metryka("vllm:num_requests_running", "vllm:num_requests_running") is None


class TestIstniejacyPrzodek:
    def test_istniejacy_katalog_zwracany_wprost(self, tmp_path):
        assert st._istniejacy_przodek(str(tmp_path)) == os.path.abspath(str(tmp_path))

    def test_schodzi_do_istniejacego_rodzica(self, tmp_path):
        # Katalog dokumentów świeżej instancji jeszcze nie istnieje, ale leży
        # na tym samym wolumenie co jego rodzic — pomiar jest nadal prawdziwy.
        brakujacy = tmp_path / "jeszcze" / "nie" / "ma"
        assert st._istniejacy_przodek(str(brakujacy)) == os.path.abspath(str(tmp_path))

    def test_sciezka_pusta_daje_korzen(self):
        assert st._istniejacy_przodek("") == os.path.abspath(os.sep)


class TestZbierz:
    def test_drugi_odczyt_idzie_z_pamieci(self, monkeypatch):
        wywolania = {"n": 0}

        def liczacy():
            wywolania["n"] += 1
            return {"online": True}

        monkeypatch.setattr(st, "_docling", liczacy)
        monkeypatch.setattr(st, "_vllm", lambda: {"online": True, "running": 0, "waiting": 0})
        monkeypatch.setattr(st, "_baza", lambda db: {"online": True, "ms": 1.0})
        monkeypatch.setattr(st, "_dysk", lambda db: {"dostepny": False, "documents_bytes": 0})

        st.zbierz(None)
        st.zbierz(None)
        assert wywolania["n"] == 1, "drugie wejście na Dashboard nie może odpytywać Sparka na nowo"

    def test_parser_offline_gdy_pada_jedna_z_dwoch_uslug(self, monkeypatch):
        # Docling wyciąga tekst, vLLM go rozumie. Bez którejkolwiek przetwarzanie
        # stoi, więc wspólny status musi być „offline", nawet gdy druga żyje.
        monkeypatch.setattr(st, "_docling", lambda: {"online": False})
        monkeypatch.setattr(st, "_vllm", lambda: {"online": True, "running": 0, "waiting": 0})
        monkeypatch.setattr(st, "_baza", lambda db: {"online": True, "ms": 1.0})
        monkeypatch.setattr(st, "_dysk", lambda db: {"dostepny": False, "documents_bytes": 0})

        parser = st.zbierz(None)["parser"]
        assert parser["online"] is False
        assert parser["docling"] is False and parser["model"] is True
