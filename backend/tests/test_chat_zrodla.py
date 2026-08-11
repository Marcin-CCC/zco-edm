"""Testy przypisywania źródeł odpowiedzi do dokumentów.

Uruchom: pytest backend/tests/test_chat_zrodla.py -v

Regresja z 2026-08-10: nazwa pliku NIE JEST identyfikatorem dokumentu. W bazie ZCO
9 nazw powtarza się i obejmuje 18 plików — pod „1.pdf" leżą dwa różne zarządzenia.
Dopasowanie po nazwie sklejało je w jedno i cytowanie prowadziło do niewłaściwego
dokumentu (odpowiedź ze strony 4 dokumentu 1/2010, odnośnik do 1/2009, który ma
jedną stronę).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.router import _enrich_with_file_ids
from app.database import Base
from app.models import File as FileModel, DocumentStatus, User, UserRole


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sesja = sessionmaker(bind=engine)()
    u = User(email="a@b.pl", username="t", hashed_password="x", role=UserRole.ADMIN)
    sesja.add(u)
    sesja.commit()
    # Dwa RÓŻNE dokumenty o tej samej nazwie — sedno regresji.
    sesja.add_all([
        FileModel(id=279, filename="1.pdf", file_path="/a/1.pdf", uploaded_by=u.id,
                  status=DocumentStatus.READY, folder_id=62,
                  metadata_={"doc_type": "zarzadzenie",
                             "doc_fields": {"numer_dokumentu": "1/2009"}}),
        FileModel(id=290, filename="1.pdf", file_path="/b/1.pdf", uploaded_by=u.id,
                  status=DocumentStatus.READY, folder_id=63,
                  metadata_={"doc_type": "zarzadzenie",
                             "doc_fields": {"numer_dokumentu": "1/2010"}}),
        FileModel(id=300, filename="regulamin.pdf", file_path="/c/r.pdf", uploaded_by=u.id,
                  status=DocumentStatus.READY, folder_id=1,
                  metadata_={"doc_type": "regulamin",
                             "doc_fields": {"numer_dokumentu": "5/2026"}}),
    ])
    sesja.commit()
    yield sesja
    sesja.close()


class TestIdentyfikacjaPoFileId:
    def test_file_id_z_n8n_rozstrzyga(self, db):
        """Gdy n8n przysyła file_id, nazwa nie ma nic do rzeczy — nawet gdy myląca."""
        zrodla = [{"filename": "1.pdf", "page": 4, "file_id": 290}]
        wynik = _enrich_with_file_ids(zrodla, db)
        assert wynik[0]["file_id"] == 290
        assert wynik[0]["doc_key"] == "1/2010"

    def test_dwa_zrodla_o_tej_samej_nazwie_to_rozne_dokumenty(self, db):
        zrodla = [{"filename": "1.pdf", "page": 4, "file_id": 290},
                  {"filename": "1.pdf", "page": 1, "file_id": 279}]
        wynik = _enrich_with_file_ids(zrodla, db)
        assert [z["doc_key"] for z in wynik] == ["1/2010", "1/2009"]


class TestNazwyNiejednoznacznej:
    def test_bez_file_id_niejednoznaczna_nazwa_nie_dostaje_odnosnika(self, db):
        """Lepiej pokazać samą nazwę niż odesłać do niewłaściwego dokumentu —
        frontend rysuje odnośnik wyłącznie wtedy, gdy jest `file_id`."""
        wynik = _enrich_with_file_ids([{"filename": "1.pdf", "page": 4}], db)
        assert "file_id" not in wynik[0] or wynik[0].get("file_id") is None
        assert "doc_key" not in wynik[0]

    def test_nazwa_jednoznaczna_dziala_jak_dotad(self, db):
        """Zgodność wstecz: dopóki n8n nie przysyła file_id, nazwy unikalne
        (czyli zdecydowana większość) mają działać bez zmian."""
        wynik = _enrich_with_file_ids([{"filename": "regulamin.pdf", "page": 2}], db)
        assert wynik[0]["file_id"] == 300
        assert wynik[0]["doc_key"] == "5/2026"

    def test_mieszanka_pewnych_i_niepewnych(self, db):
        zrodla = [
            {"filename": "1.pdf", "page": 4},                    # niejednoznaczna
            {"filename": "regulamin.pdf", "page": 1},            # jednoznaczna
            {"filename": "1.pdf", "page": 4, "file_id": 290},    # pewna
        ]
        wynik = _enrich_with_file_ids(zrodla, db)
        assert wynik[0].get("file_id") is None
        assert wynik[1]["file_id"] == 300
        assert wynik[2]["file_id"] == 290


class TestOdpornosci:
    def test_zrodlo_bez_nazwy_i_bez_id_przechodzi(self, db):
        assert _enrich_with_file_ids([{"page": 3}], db) == [{"page": 3}]

    def test_pusta_lista(self, db):
        assert _enrich_with_file_ids([], db) == []

    def test_nieistniejacy_file_id_nie_wywala(self, db):
        wynik = _enrich_with_file_ids([{"filename": "x.pdf", "file_id": 9999}], db)
        assert wynik[0]["file_id"] == 9999      # zostaje, ale bez etykiety typu
        assert "doc_key" not in wynik[0]
