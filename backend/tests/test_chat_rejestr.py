"""Testy rejestru pytań i listy pytających (zakładka „Wszystkie pytania").

Uruchom: pytest backend/tests/test_chat_rejestr.py -v

Powód powstania: oba te zestawienia zwracały rolę użytkownika przez `rola.value` —
składnię z czasów, gdy rola była enumem Pythona. Po migracji na `String` (wersja
1.1.0) `users.role` jest zwykłym napisem, więc `.value` wywracało endpoint błędem
500. Rejestr przestał się otwierać w ogóle, a lista pytających gasła po cichu, bo
frontend łyka jej błąd — filtr osoby po prostu pokazywał samo „wszyscy".

Testy wołają funkcje endpointów wprost, bez HTTP: sprawdzamy zawartość odpowiedzi,
a nie routing.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.router import rejestr_pytan, uzytkownicy_pytajacy
from app.database import Base
from app.models import ROLE_ADMIN, ROLE_GUEST, Conversation, Message, User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sesja = sessionmaker(bind=engine)()
    yield sesja
    sesja.close()


@pytest.fixture
def admin(db):
    u = User(email="admin@szpital.pl", username="admin", hashed_password="x", role=ROLE_ADMIN)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def rozmowa(db):
    """Jedna tura: pytanie użytkownika i odpowiedź modelu."""
    pytajacy = User(email="lekarz@szpital.pl", username="lekarz", full_name="Jan Kowalski",
                    hashed_password="x", role="DOCTOR")
    db.add(pytajacy)
    db.commit()
    conv = Conversation(user_id=pytajacy.id, title="Rozmowa")
    db.add(conv)
    db.commit()
    db.add(Message(conversation_id=conv.id, role="user", content="Ile dni urlopu?"))
    db.add(Message(conversation_id=conv.id, role="assistant", content="Dwadzieścia sześć.",
                   sources=[{"filename": "Regulamin.pdf", "page": 3, "file_id": 12, "cited": True}]))
    db.commit()
    return conv


class TestRejestruPytan:
    def test_rola_wraca_jako_kod_nie_enum(self, db, admin, rozmowa):
        """Rola jest napisem od migracji enum→varchar; `.value` na niej się wywraca."""
        wynik = rejestr_pytan(db=db, current_user=admin)
        assert wynik["pytania"][0]["rola"] == "DOCTOR"

    def test_para_pytanie_odpowiedz(self, db, admin, rozmowa):
        wpis = rejestr_pytan(db=db, current_user=admin)["pytania"][0]
        assert wpis["pytanie"] == "Ile dni urlopu?"
        assert wpis["odpowiedz"] == "Dwadzieścia sześć."
        assert wpis["uzytkownik"] == "Jan Kowalski"

    def test_zrodla_z_identyfikatorem_pliku(self, db, admin, rozmowa):
        """Bez `file_id` nie da się otworzyć dokumentu z poziomu rejestru."""
        zrodla = rejestr_pytan(db=db, current_user=admin)["pytania"][0]["zrodla"]
        assert zrodla == [{"filename": "Regulamin.pdf", "page": 3, "file_id": 12, "cited": True}]

    def test_zestawienie_wg_roli(self, db, admin, rozmowa):
        assert rejestr_pytan(db=db, current_user=admin)["wg_roli"] == {"DOCTOR": 1}

    def test_rozmowa_bez_wlasciciela_nie_wywraca(self, db, admin):
        """`outerjoin` z użytkownikiem może dać None — rejestr ma to znieść."""
        conv = Conversation(user_id=999, title="Sierota")
        db.add(conv)
        db.commit()
        db.add(Message(conversation_id=conv.id, role="assistant", content="x"))
        db.commit()
        wynik = rejestr_pytan(db=db, current_user=admin)
        assert wynik["pytania"][0]["rola"] is None
        assert wynik["wg_roli"] == {"?": 1}

    def test_tylko_dla_administratora(self, db):
        zwykly = User(email="z@b.pl", username="zwykly", hashed_password="x", role=ROLE_GUEST)
        db.add(zwykly)
        db.commit()
        with pytest.raises(Exception) as e:
            rejestr_pytan(db=db, current_user=zwykly)
        assert "403" in str(e.value) or "administrator" in str(e.value).lower()


class TestListyPytajacych:
    def test_rola_wraca_jako_kod_nie_enum(self, db, admin, rozmowa):
        """Ten sam błąd co w rejestrze, ale objawiał się pustym filtrem, nie komunikatem."""
        wynik = uzytkownicy_pytajacy(db=db, current_user=admin)
        assert wynik["uzytkownicy"] == [{"id": rozmowa.user_id, "nazwa": "Jan Kowalski",
                                         "rola": "DOCTOR"}]

    def test_tylko_ci_co_pytali(self, db, admin, rozmowa):
        """Admin nie zadał żadnego pytania, więc nie ma go w filtrze."""
        nazwy = [u["nazwa"] for u in uzytkownicy_pytajacy(db=db, current_user=admin)["uzytkownicy"]]
        assert nazwy == ["Jan Kowalski"]
