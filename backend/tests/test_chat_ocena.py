"""Testy oceny odpowiedzi (kciuk w górę / neutralnie / w dół).

Uruchom: pytest backend/tests/test_chat_ocena.py -v

Ocena ma posłużyć za materiał do zestawu kontrolnego (app/retrieval_bench.py), więc
testy pilnują przede wszystkim TRWAŁOŚCI zgłoszenia i kompletu kontekstu — bez tego
zgłoszenie „zła odpowiedź" jest za tydzień bezużyteczne.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.router import OCENY_DOZWOLONE, POWODY, zapisz_ocene
from app.database import Base
from app.models import ROLE_GUEST, OcenaOdpowiedzi, User
from app.schemas import OcenaCreate


@pytest.fixture
def db():
    """Pusta baza w pamięci — wystarcza, bo sprawdzamy logikę zapisu, nie SQL."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sesja = sessionmaker(bind=engine)()
    yield sesja
    sesja.close()


@pytest.fixture
def uzytkownik(db):
    u = User(email="a@b.pl", username="tester", hashed_password="x", role=ROLE_GUEST)
    db.add(u)
    db.commit()
    return u


class TestSlownikOcen:
    def test_trzy_stopnie(self):
        assert OCENY_DOZWOLONE == {"dobra", "neutralna", "zla"}

    def test_kazdy_powod_wskazuje_inna_czesc_systemu(self):
        """Powody nie są ozdobą: samo ich zliczanie ma mówić, gdzie szukać przyczyny."""
        assert set(POWODY) == {"nieprawda", "nie_znalazl", "niepelna", "nie_o_to"}
        assert all(isinstance(v, str) and v for v in POWODY.values())


class TestSchematu:
    def test_minimalne_zgloszenie(self):
        o = OcenaCreate(ocena="dobra")
        assert o.ocena == "dobra" and o.powod is None and o.message_id is None

    def test_pelne_zgloszenie(self):
        o = OcenaCreate(ocena="zla", powod="nie_znalazl", message_id=7,
                        request_id="abc", pytanie="p", odpowiedz="o")
        assert (o.powod, o.message_id, o.request_id) == ("nie_znalazl", 7, "abc")


class TestTrwalosci:
    """Zgłoszenie musi przeżyć skasowanie rozmowy — inaczej znika dokładnie wtedy,
    gdy użytkownik sprząta po nieudanej sesji, czyli w najciekawszych przypadkach."""

    @pytest.mark.parametrize("kolumna", ["message_id", "user_id"])
    def test_klucze_obce_ustawiaja_null_zamiast_kasowac(self, kolumna):
        fk = list(OcenaOdpowiedzi.__table__.c[kolumna].foreign_keys)[0]
        assert fk.ondelete == "SET NULL", (
            f"{kolumna}: kasowanie rozmowy lub konta nie może zabierać ze sobą oceny"
        )

    def test_kopia_tresci_jest_w_tabeli(self):
        """Sama referencja do wiadomości nie wystarczy — po jej usunięciu zostałby
        werdykt bez pytania i odpowiedzi, czyli nic."""
        kolumny = {c.name for c in OcenaOdpowiedzi.__table__.columns}
        assert {"pytanie", "odpowiedz", "diagnostyka"} <= kolumny

class TestLiczySieOstatniaOcena:
    """Zgłoszony defekt: przeklikiwanie ikon zapisywało KAŻDE kliknięcie. Pomyłkowe
    trafienie w ikonę zostawało w danych na równi z oceną przemyślaną, a dopisanie
    powodu do oceny negatywnej liczyło ją drugi raz."""

    def zapisz(self, db, uzytkownik, **kwargs):
        return zapisz_ocene(OcenaCreate(**kwargs), db=db, current_user=uzytkownik)

    def test_zmiana_zdania_nadpisuje(self, db, uzytkownik):
        for ocena in ("dobra", "neutralna", "zla"):
            self.zapisz(db, uzytkownik, ocena=ocena, message_id=11, pytanie="ile urlopu?")
        wiersze = db.query(OcenaOdpowiedzi).all()
        assert len(wiersze) == 1
        assert wiersze[0].ocena == "zla"

    def test_powod_nie_tworzy_drugiego_wpisu(self, db, uzytkownik):
        self.zapisz(db, uzytkownik, ocena="zla", message_id=11, pytanie="ile urlopu?")
        self.zapisz(db, uzytkownik, ocena="zla", powod="nie_znalazl",
                    message_id=11, pytanie="ile urlopu?")
        wiersze = db.query(OcenaOdpowiedzi).all()
        assert len(wiersze) == 1 and wiersze[0].powod == "nie_znalazl"

    def test_powrot_do_oceny_pozytywnej_czysci_powod(self, db, uzytkownik):
        self.zapisz(db, uzytkownik, ocena="zla", powod="niepelna", message_id=11)
        self.zapisz(db, uzytkownik, ocena="dobra", message_id=11)
        wiersz = db.query(OcenaOdpowiedzi).one()
        assert (wiersz.ocena, wiersz.powod) == ("dobra", None)

    def test_ocena_przed_zapisem_historii_zostaje_polaczona(self, db, uzytkownik):
        """Pierwsze kliknięcie potrafi wyprzedzić zapis tury — wtedy nie ma jeszcze
        message_id. Drugie kliknięcie już go ma i musi trafić w ten sam wiersz."""
        self.zapisz(db, uzytkownik, ocena="neutralna", pytanie="ile urlopu?")
        self.zapisz(db, uzytkownik, ocena="zla", powod="nie_o_to",
                    message_id=42, pytanie="ile urlopu?")
        wiersz = db.query(OcenaOdpowiedzi).one()
        assert (wiersz.ocena, wiersz.powod, wiersz.message_id) == ("zla", "nie_o_to", 42)

    def test_rozne_odpowiedzi_to_rozne_oceny(self, db, uzytkownik):
        self.zapisz(db, uzytkownik, ocena="dobra", message_id=11, pytanie="a?")
        self.zapisz(db, uzytkownik, ocena="zla", message_id=12, pytanie="b?")
        assert db.query(OcenaOdpowiedzi).count() == 2

    def test_nieznana_ocena_odrzucona(self, db, uzytkownik):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            self.zapisz(db, uzytkownik, ocena="swietna", message_id=11)

    def test_nieznany_powod_pomijany(self, db, uzytkownik):
        self.zapisz(db, uzytkownik, ocena="zla", powod="cokolwiek", message_id=11)
        assert db.query(OcenaOdpowiedzi).one().powod is None


class TestTrwalosciCd:
    def test_diagnostyka_jest_polem_swobodnym(self):
        """Migawka planu zmienia kształt razem z wyszukiwaniem, więc trzymamy JSON,
        a nie kolumny — inaczej każda zmiana mechanizmu wymagałaby migracji."""
        typ = OcenaOdpowiedzi.__table__.c["diagnostyka"].type
        assert typ.__class__.__name__.upper().startswith("JSON")
