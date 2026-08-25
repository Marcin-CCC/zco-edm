"""Testy komunikatów błędów w języku interfejsu (krok 5 wielojęzyczności).

Uruchom: pytest backend/tests/test_komunikaty_bledow.py -v

Router podaje KLUCZ, bo w miejscu, gdzie powstaje błąd, języka żądania się nie zna.
Tłumaczenie dokłada się raz, przy zamianie wyjątku na odpowiedź. Na drut idzie
zwykły napis — dla frontendu i każdego innego klienta nic się nie zmienia i ta
przezroczystość jest tu najważniejsza: obsługa wyjątków dotyka WSZYSTKICH błędów
aplikacji, także tych, których nie oznaczyliśmy sami.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.locales import SUPPORTED_LOCALES
from app.main import NAGLOWEK_JEZYKA, obsluz_wyjatek_http
from app.messages import KATALOG, UserMessage, render


@pytest.fixture(scope="module")
def klient():
    """Mała aplikacja z TĄ SAMĄ obsługą wyjątków co produkcyjna."""
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, obsluz_wyjatek_http)

    @app.get("/z-kluczem")
    def z_kluczem():
        raise HTTPException(status_code=403, detail=UserMessage("common.adminOnly"))

    @app.get("/z-wartoscia")
    def z_wartoscia():
        raise HTTPException(status_code=413, detail=UserMessage("files.tooLarge", limit="100 MB"))

    @app.get("/techniczny")
    def techniczny():
        raise HTTPException(status_code=400, detail="Parent folder not found.")

    return TestClient(app, raise_server_exceptions=False)


class TestOdpowiedzi:
    def test_bez_naglowka_po_polsku(self, klient):
        odp = klient.get("/z-kluczem")
        assert odp.status_code == 403
        assert odp.json()["detail"] == "Tylko administrator."

    def test_naglowek_przestawia_jezyk(self, klient):
        odp = klient.get("/z-kluczem", headers={NAGLOWEK_JEZYKA: "en"})
        assert odp.json()["detail"] == "Administrators only."

    def test_wartosci_wchodza_do_komunikatu(self, klient):
        odp = klient.get("/z-wartoscia", headers={NAGLOWEK_JEZYKA: "en"})
        assert odp.json()["detail"] == "The file is too large. The maximum size is 100 MB."

    def test_komunikat_techniczny_przechodzi_nietkniety(self, klient):
        """Obsługa MUSI być przezroczysta dla wszystkiego, czego nie oznaczyliśmy —
        wyjątków bibliotek, 404 tras, komunikatów dla administratora."""
        assert klient.get("/techniczny").json()["detail"] == "Parent folder not found."

    def test_nieznana_trasa_nadal_daje_404(self, klient):
        assert klient.get("/nie-ma-takiej").status_code == 404

    # Same znaki ASCII — nagłówek HTTP z polskimi literami odrzuca już klient,
    # więc taki przypadek nie mówiłby nic o aplikacji.
    @pytest.mark.parametrize("naglowek", ["", "de-DE", "klingon", "xx", "pl;q=0.9,en"])
    def test_dziwny_naglowek_nie_wywraca_odpowiedzi(self, klient, naglowek):
        """Nagłówek przychodzi z zewnątrz — nie wolno mu wywrócić obsługi błędu."""
        odp = klient.get("/z-kluczem", headers={NAGLOWEK_JEZYKA: naglowek})
        assert odp.status_code == 403 and odp.json()["detail"]


class TestKatalogu:
    def test_polski_i_angielski_maja_te_same_klucze(self):
        rozjazd = set(KATALOG["pl"]) ^ set(KATALOG["en"])
        assert not rozjazd, f"klucze tylko w jednym języku: {sorted(rozjazd)}"

    def test_brak_klucza_daje_klucz_a_nie_wyjatek(self):
        """Dodanie komunikatu bez wpisu w katalogu ma być widoczne od razu,
        ale nie może wywrócić żądania wyjątkiem w obsłudze wyjątku."""
        assert render(UserMessage("nie.ma.takiego"), "pl") == "nie.ma.takiego"

    def test_niezgodne_pola_nie_wywracaja(self):
        """Literówka w nazwie pola nie może zamienić błędu 400 w błąd 500."""
        assert render(UserMessage("files.tooLarge", zle_pole="x"), "pl")

    @pytest.mark.parametrize("kod", SUPPORTED_LOCALES)
    def test_kazdy_jezyk_cos_zwraca(self, kod):
        """Języki bez własnego katalogu spadają na polski — nigdy na sam klucz."""
        tekst = render(UserMessage("common.adminOnly"), kod)
        assert tekst and tekst != "common.adminOnly"
