"""Testy payloadu webhooka parsowania.

Uruchom: pytest backend/tests/test_webhook_payload.py -v

Jeden workflow n8n obsługuje OBA wdrożenia (ZCO i demo), więc payload jest jedynym
miejscem, z którego n8n wie, czyj to plik i do której bazy ma trafić. Brak nazwy
instancji w raporcie e-mail kosztował 2026-08-10 szukanie pliku w niewłaściwej bazie.
"""
from app.config import settings
from app.files.router import build_webhook_payload


class TestPayloadu:
    def test_ma_komplet_pol(self):
        p = build_webhook_payload(7, "/data/x.pdf", folder_id=3, uzytkownik="Piotr Piątek")
        assert p["file_id"] == 7
        assert p["file_path"] == "/data/x.pdf"
        assert p["folder_id"] == 3
        assert p["collection"] == settings.QDRANT_COLLECTION
        assert p["instancja"] == settings.APP_NAME
        assert p["uzytkownik"] == "Piotr Piątek"
        assert p["status_update_url"].endswith("/api/webhook/file/7/status")

    def test_katalog_glowny_to_none(self):
        assert build_webhook_payload(1, "/x.pdf")["folder_id"] is None

    def test_brak_uzytkownika_nie_daje_pustego_pola(self):
        """W raporcie e-mail puste miejsce po autorze wygląda na usterkę szablonu,
        a nie na brak danych — dlatego wstawiamy słowo, nie pusty string."""
        assert build_webhook_payload(1, "/x.pdf")["uzytkownik"] == "nieznany"
        assert build_webhook_payload(1, "/x.pdf", uzytkownik="")["uzytkownik"] == "nieznany"

    def test_nazwa_instancji_nigdy_pusta(self):
        """n8n wstawia ją w temat maila w nawiasie kwadratowym — pusty nawias byłby
        gorszy niż brak zmiany, bo wyglądałby na zepsuty szablon."""
        assert build_webhook_payload(1, "/x.pdf")["instancja"]
