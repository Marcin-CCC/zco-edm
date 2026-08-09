"""Testy oceny odpowiedzi (kciuk w górę / neutralnie / w dół).

Uruchom: pytest backend/tests/test_chat_ocena.py -v

Ocena ma posłużyć za materiał do zestawu kontrolnego (app/retrieval_bench.py), więc
testy pilnują przede wszystkim TRWAŁOŚCI zgłoszenia i kompletu kontekstu — bez tego
zgłoszenie „zła odpowiedź" jest za tydzień bezużyteczne.
"""
import pytest

from app.chat.router import OCENY_DOZWOLONE, POWODY
from app.models import OcenaOdpowiedzi
from app.schemas import OcenaCreate


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

    def test_diagnostyka_jest_polem_swobodnym(self):
        """Migawka planu zmienia kształt razem z wyszukiwaniem, więc trzymamy JSON,
        a nie kolumny — inaczej każda zmiana mechanizmu wymagałaby migracji."""
        typ = OcenaOdpowiedzi.__table__.c["diagnostyka"].type
        assert typ.__class__.__name__.upper().startswith("JSON")
