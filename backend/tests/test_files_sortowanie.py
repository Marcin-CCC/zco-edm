"""Testy kolejności listy plików — sortowanie po kliknięciu w nagłówek kolumny.

Uruchom: pytest backend/tests/test_files_sortowanie.py -v

Sprawdzamy SQL, który powstaje, a nie wynik na danych: układanie wierszy to robota
bazy i ta jest zmierzona na produkcji. Tu pilnujemy rzeczy, które łatwo zepsuć
niezauważenie — bo lista posortowana ODROBINĘ inaczej niż trzeba wygląda jak
działająca.

Silnik Postgresa tworzymy bez łączenia się z czymkolwiek: `create_engine` nie
otwiera połączenia, dopóki nie wykonamy zapytania, a my tylko kompilujemy.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app import schema_upgrade
from app.files.router import SORT_KEYS, apply_sort
from app.models import File as FileModel

PG = postgresql.dialect()


@pytest.fixture(autouse=True)
def kolacja_wylaczona():
    """Flaga kolacji to stan MODUŁU, wspólny dla całego przebiegu pytesta.

    Inne testy podnoszą aplikację przez `TestClient`, co uruchamia uaktualnienia
    startowe na lokalnym Postgresie i flagę włącza — całkiem słusznie. Bez pinezki
    wynik tych testów zależałby więc od kolejności plików w przebiegu.
    """
    poprzednia = schema_upgrade._collation_ready
    schema_upgrade._collation_ready = False
    yield
    schema_upgrade._collation_ready = poprzednia


@pytest.fixture
def db():
    """Sesja wskazująca Postgresa — bez połączenia, do samego kompilowania SQL-a."""
    sesja = Session(bind=create_engine("postgresql+psycopg2://nikt@localhost/nic"))
    yield sesja
    sesja.close()


def sql(db, sort_by: str, order: str = "asc") -> str:
    zapytanie = apply_sort(db.query(FileModel), sort_by, order, db)
    return str(zapytanie.statement.compile(dialect=PG)).replace("\n", " ")


def order_by(db, sort_by: str, order: str = "asc") -> str:
    return sql(db, sort_by, order).split("ORDER BY", 1)[1].strip()


class TestBialejListy:
    def test_klucze_odpowiadaja_kolumnom_tabeli(self):
        assert SORT_KEYS == ("name", "type", "size", "category", "date")

    def test_nieznany_klucz_nie_wywraca_i_wraca_do_nazwy(self, db):
        """Adres można wpisać ręcznie. Nieznana wartość ma dać kolejność domyślną,
        a nie błąd 500 ani — tym bardziej — trafić do SQL-a."""
        assert "files.filename" in order_by(db, "'; drop table files; --")

    def test_wartosc_z_adresu_nie_trafia_do_sql(self, db):
        assert "drop table" not in sql(db, "'; drop table files; --").lower()


class TestKluczaGlownego:
    def test_rozmiar(self, db):
        assert order_by(db, "size").startswith("files.size ASC")

    def test_data(self, db):
        assert order_by(db, "date").startswith("files.created_at ASC")

    def test_typ_po_rozszerzeniu_nie_po_mime(self, db):
        """Kolumna Typ pokazuje ikonę dobraną po rozszerzeniu — `mime_type` dałby
        kolejność wg „application/vnd.openxml…", czyli niezgodną z tym, co widać."""
        wyrazenie = order_by(db, "type").lower()
        assert "substring(files.filename from" in wyrazenie
        assert "mime_type" not in wyrazenie

    def test_kategoria_po_nazwie_typu_z_rejestru(self, db):
        """Nie po slugu: administrator może typ przemianować i wtedy kolejność
        rozjechałaby się z etykietami w tabeli."""
        zapytanie = sql(db, "category")
        assert "doc_type_schemas" in zapytanie
        assert "LEFT OUTER JOIN" in zapytanie
        assert "doc_type_schemas.name" in zapytanie

    def test_kategoria_traktuje_inny_jak_brak(self, db):
        """Tabela pokazuje dla „inny" napis „nierozpoznana", więc przy sortowaniu
        ma to być pustka, a nie kategoria o nazwie „inny" wśród liter."""
        assert "nullif" in order_by(db, "category").lower()


class TestKierunku:
    @pytest.mark.parametrize("klucz", ["name", "type", "size", "category", "date"])
    def test_malejaco_odwraca_klucz_glowny(self, db, klucz):
        assert " DESC" in order_by(db, klucz, "desc")

    @pytest.mark.parametrize("klucz", ["name", "type", "size", "category", "date"])
    def test_puste_zawsze_na_koncu(self, db, klucz):
        """Bez NULLS LAST odwrócenie kolejności wypycha na górę listy pliki bez
        rozmiaru albo bez rozpoznanej kategorii — czyli same puste komórki."""
        assert "NULLS LAST" in order_by(db, klucz, "desc")
        assert "NULLS LAST" in order_by(db, klucz, "asc")


class TestRemisow:
    @pytest.mark.parametrize("klucz", ["type", "size", "category", "date"])
    def test_nazwa_jest_drugim_kluczem(self, db, klucz):
        """Pliki o tym samym rozmiarze czy dacie bez tego układają się w kolejności
        przypadkowej i ZMIENNEJ między odświeżeniami.

        Sprawdzamy KOŃCÓWKĘ, a nie podział po przecinkach: wyrażenie kategorii
        jest `CASE`, więc ma własne przecinki w środku.
        """
        assert order_by(db, klucz).endswith("files.filename ASC, files.id ASC")

    def test_przy_sortowaniu_po_nazwie_nie_powtarzamy_nazwy(self, db):
        assert order_by(db, "name") == "files.filename ASC NULLS LAST, files.id ASC"


class TestKolacji:
    def test_nazwa_uzywa_kolacji_gdy_jest(self, db):
        schema_upgrade._collation_ready = True      # sprząta fixture `kolacja_wylaczona`
        assert schema_upgrade.NAME_COLLATION in order_by(db, "name")
        # Także jako drugi klucz — inaczej remisy układałyby się bajtami.
        assert schema_upgrade.NAME_COLLATION in order_by(db, "size")

    def test_kategoria_tez_po_polsku(self, db):
        """Nazwy kategorii są polskie, więc bajtowo „Załącznik" wypada PO
        „Zarządzeniu" (`ł` jest dwubajtowe) — odwrotnie niż w alfabecie.
        Zmierzone na danych ZCO, zanim kolacja objęła ten klucz."""
        schema_upgrade._collation_ready = True
        klucz_glowny = order_by(db, "category").split("NULLS LAST")[0]
        assert schema_upgrade.NAME_COLLATION in klucz_glowny
