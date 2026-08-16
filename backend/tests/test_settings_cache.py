"""Test pamięci podręcznej ustawień aplikacji.

Uruchom: pytest backend/tests/test_settings_cache.py -v

Powód istnienia: przy sprzątaniu ostrzeżeń lintera z modułu ustawień łatwo usunąć
deklarację `global _settings_cache` z `_load_cache_from_db`. Wygląda ona na zbędną
(w pozostałych funkcjach tego modułu naprawdę jest), ale akurat ta jedna podstawia
CAŁY słownik pod nazwę. Bez `global` przypisanie tworzy zmienną lokalną, pamięć
podręczna zostaje pusta, a aplikacja po cichu jedzie na wartościach domyślnych:
adresie webhooka, nazwie instancji, liście rozszerzeń. Nic nie wybucha — po prostu
ustawienia administratora przestają obowiązywać. Ten test to zauważa od razu.
"""
from types import SimpleNamespace

import pytest

import app.settings.router as ustawienia


class FakeQuery:
    def __init__(self, rekordy):
        self._rekordy = rekordy

    def all(self):
        return self._rekordy


class FakeSession:
    """Minimalna atrapa sesji: `_load_cache_from_db` woła tylko `query(...).all()`."""

    def __init__(self, rekordy):
        self._rekordy = rekordy

    def query(self, _model):
        return FakeQuery(self._rekordy)


@pytest.fixture
def czysta_pamiec():
    """Zdejmuje i przywraca stan modułu — testy nie mogą sobie nawzajem podmieniać
    ustawień działającej aplikacji."""
    kopia = dict(ustawienia._settings_cache)
    zaladowane = ustawienia._cache_loaded
    yield
    ustawienia._settings_cache = kopia
    ustawienia._cache_loaded = zaladowane


def wiersze(**pary):
    return [SimpleNamespace(key=k, value=v) for k, v in pary.items()]


def test_wczytanie_wypelnia_pamiec_modulu(czysta_pamiec):
    ustawienia._settings_cache = {}
    ustawienia._cache_loaded = False

    ustawienia._load_cache_from_db(FakeSession(wiersze(app_name="ZCO DM", smtp_host="poczta.example")))

    assert ustawienia._settings_cache["app_name"] == "ZCO DM", (
        "pamięć podręczna modułu jest pusta — najpewniej zniknęła deklaracja "
        "`global _settings_cache` z _load_cache_from_db"
    )
    assert ustawienia._cache_loaded is True


def test_odczyt_bierze_wartosc_z_bazy_a_nie_domyslna(czysta_pamiec):
    ustawienia._settings_cache = {}
    ustawienia._cache_loaded = False

    ustawienia._load_cache_from_db(FakeSession(wiersze(allowed_extensions="pdf,odt")))

    assert ustawienia.ustawienie("allowed_extensions", "pdf,docx,xlsx") == "pdf,odt"


def test_brakujacy_klucz_schodzi_do_wartosci_domyslnej(czysta_pamiec):
    ustawienia._settings_cache = {}
    ustawienia._cache_loaded = False

    ustawienia._load_cache_from_db(FakeSession([]))

    assert ustawienia.ustawienie("smtp_host", "brak") == "brak"
