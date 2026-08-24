"""Testy kolejności plików na liście (ekran Pliki).

Uruchom: pytest backend/tests/test_sortowanie_nazw.py -v

Dlaczego to w ogóle wymaga kolacji: obraz bazy stoi na Alpine, a więc na musl,
które nie implementuje kolacji językowych. Zwykłe `ORDER BY` schodzi tam do
porządku bajtowego i układa listę tak, że zarządzenie nr 2 stoi po nr 19,
a nazwy z ogonkami lądują za całym alfabetem.

Tu sprawdzamy dwie rzeczy, których nie da się sprawdzić na SQLite:
kiedy sortowanie ma użyć kolacji, i czy jej brak nie wywraca listy. Sam WYNIK
sortowania sprawdza baza — zmierzony na produkcji przy wdrożeniu.
"""
import importlib

import pytest
from sqlalchemy import create_engine

from app import schema_upgrade
from app.models import File as FileModel
from app.schema_upgrade import (NAME_COLLATION, create_name_collation,
                                name_collation_available)


@pytest.fixture(autouse=True)
def czysta_flaga():
    """Flaga jest stanem modułu — bez zerowania testy zależałyby od kolejności."""
    poprzednia = schema_upgrade._collation_ready
    schema_upgrade._collation_ready = False
    yield
    schema_upgrade._collation_ready = poprzednia


class TestZakladaniaKolacji:
    def test_poza_postgresem_nic_nie_robi(self):
        """SQLite nie zna `CREATE COLLATION` — próba musi zostać pominięta, nie rzucić."""
        create_name_collation(create_engine("sqlite://"))
        assert name_collation_available() is False

    def test_nazwa_kolacji_bez_znakow_wymagajacych_cytowania(self):
        """`.collate()` wstawia nazwę do SQL-a wprost; myślnik wymagałby cudzysłowów."""
        assert NAME_COLLATION.replace("_", "").isalnum()
        assert NAME_COLLATION.islower()


class TestZapytaniaOListe:
    """Zapytanie ma użyć kolacji tylko wtedy, gdy ta jest gotowa."""

    def _sql(self) -> str:
        from app.files.router import name_collation_available as dostepna
        nazwa = FileModel.filename
        if dostepna():
            nazwa = nazwa.collate(NAME_COLLATION)
        return str(nazwa.asc())

    def test_bez_kolacji_zwykly_order_by(self):
        assert NAME_COLLATION not in self._sql()
        assert "filename" in self._sql()

    def test_z_kolacja_trafia_do_sql(self):
        schema_upgrade._collation_ready = True
        assert NAME_COLLATION in self._sql()

    def test_router_czyta_flage_na_biezaco(self):
        """Router importuje FUNKCJĘ, nie wartość — inaczej złapałby `False` z chwili
        importu, czyli sprzed uruchomienia uaktualnień startowych, i kolacja nigdy
        by się nie włączyła."""
        # `app.files` wystawia pod nazwą `router` obiekt APIRouter, który przesłania
        # moduł o tej samej nazwie — po moduł trzeba więc sięgnąć wprost.
        modul = importlib.import_module("app.files.router")
        assert modul.name_collation_available() is False
        schema_upgrade._collation_ready = True
        assert modul.name_collation_available() is True
