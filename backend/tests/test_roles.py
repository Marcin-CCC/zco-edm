"""Testy słownika ról i reguł, które trzymają spójność uprawnień.

Uruchom: pytest backend/tests/test_roles.py -v

Największym ryzykiem NIE jest to, że rola się nie doda, tylko że jej usunięcie
zostawi po sobie ślad: użytkownika bez prawidłowej roli albo osierocone uprawnienie
do folderu, które odżyje przy roli o tym samym kodzie. Stąd większość testów dotyczy
usuwania.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    AccessLevel, Folder, FolderPermission, ROLE_ADMIN, ROLE_GUEST, Role, User,
)
from app.rbac import readable_folder_ids
from app.roles.router import create_role, delete_role, list_roles, rename_role
from app.roles.service import code_from_name, ensure_role_exists, unique_code
from app.schema_upgrade import seed_roles
from app.schemas import RoleCreate, RoleRename


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_roles(session)
        yield session


@pytest.fixture
def admin(db):
    user = User(email="a@b.pl", username="admin", hashed_password="x", role=ROLE_ADMIN)
    db.add(user)
    db.commit()
    return user


def add_folder(db, name, path):
    folder = Folder(name=name, path=path, created_by=1)
    db.add(folder)
    db.commit()
    return folder


class TestCodeFromName:
    @pytest.mark.parametrize("name,expected", [
        ("Pielęgniarka", "PIELEGNIARKA"),
        ("Personel medyczny", "PERSONEL_MEDYCZNY"),
        ("  Ratownik  ", "RATOWNIK"),
        ("Dział IT / serwis", "DZIAL_IT_SERWIS"),
        ("Żłobek", "ZLOBEK"),
    ])
    def test_transliterates_and_uppercases(self, name, expected):
        assert code_from_name(name) == expected

    def test_name_without_letters_gives_empty_code(self):
        assert code_from_name("!!! ???") == ""

    def test_unique_code_adds_suffix_on_collision(self, db):
        db.add(Role(code="RATOWNIK", name="Ratownik medyczny", sort_order=100))
        db.commit()
        assert unique_code(db, "ratownik") == "RATOWNIK_2"

    def test_unique_code_rejects_name_without_letters(self, db):
        with pytest.raises(HTTPException) as e:
            unique_code(db, "###")
        assert e.value.status_code == 400


class TestSeedRoles:
    def test_creates_built_in_roles(self, db):
        codes = {r.code for r in db.query(Role).all()}
        assert {ROLE_ADMIN, ROLE_GUEST, "DOCTOR", "MEDICAL_STAFF"} <= codes

    def test_is_idempotent(self, db):
        before = db.query(Role).count()
        seed_roles(db)
        assert db.query(Role).count() == before

    def test_adopts_role_code_found_in_data(self, db):
        """Kod zastany w danych, a nieznany słownikowi, musi trafić do słownika —
        inaczej administrator nie ma jak taką rolą zarządzać ani jej usunąć."""
        db.add(User(email="n@b.pl", username="nurse", hashed_password="x", role="NURSE"))
        db.commit()
        seed_roles(db)
        adopted = db.query(Role).filter(Role.code == "NURSE").first()
        assert adopted is not None and adopted.is_system is False


class TestCreateRole:
    def test_generates_code_and_puts_role_last(self, db, admin):
        result = create_role(RoleCreate(name="Pielęgniarka"), db=db, current_user=admin)
        assert result.code == "PIELEGNIARKA"
        assert result.is_system is False
        assert result.sort_order > max(r.sort_order for r in db.query(Role).all() if r.code != "PIELEGNIARKA")

    def test_new_role_starts_without_access(self, db, admin):
        create_role(RoleCreate(name="Ratownik"), db=db, current_user=admin)
        assert db.query(FolderPermission).filter(FolderPermission.role == "RATOWNIK").count() == 0

    def test_copies_permissions_from_another_role(self, db, admin):
        folder = add_folder(db, "Kadry", "/Kadry")
        db.add(FolderPermission(folder_id=folder.id, role="DOCTOR", access_level=AccessLevel.READ))
        db.commit()

        create_role(
            RoleCreate(name="Ratownik", copy_permissions_from="DOCTOR"),
            db=db, current_user=admin,
        )
        skopiowane = db.query(FolderPermission).filter(FolderPermission.role == "RATOWNIK").all()
        assert [p.folder_id for p in skopiowane] == [folder.id]

    @pytest.mark.parametrize("name", ["Lekarz", "  lekarz  ", "LEKARZ"])
    def test_rejects_duplicate_name_regardless_of_case(self, db, admin, name):
        with pytest.raises(HTTPException) as e:
            create_role(RoleCreate(name=name), db=db, current_user=admin)
        assert e.value.status_code == 409

    def test_rejects_too_short_name(self, db, admin):
        with pytest.raises(HTTPException) as e:
            create_role(RoleCreate(name="X"), db=db, current_user=admin)
        assert e.value.status_code == 400

    def test_non_admin_is_rejected(self, db):
        intruz = User(email="g@b.pl", username="gosc", hashed_password="x", role=ROLE_GUEST)
        with pytest.raises(HTTPException) as e:
            create_role(RoleCreate(name="Ratownik"), db=db, current_user=intruz)
        assert e.value.status_code == 403


class TestRenameRole:
    def test_changes_label_and_keeps_code(self, db, admin):
        result = rename_role("DOCTOR", RoleRename(name="Lekarz specjalista"), db=db, current_user=admin)
        assert (result.code, result.name) == ("DOCTOR", "Lekarz specjalista")

    def test_system_role_can_be_renamed(self, db, admin):
        """Etykieta nic nie znaczy dla kontroli uprawnień — te patrzą na kod."""
        result = rename_role(ROLE_GUEST, RoleRename(name="Pracownik zewnętrzny"), db=db, current_user=admin)
        assert result.code == ROLE_GUEST

    def test_rejects_name_taken_by_another_role(self, db, admin):
        with pytest.raises(HTTPException) as e:
            rename_role("DOCTOR", RoleRename(name="Technik"), db=db, current_user=admin)
        assert e.value.status_code == 409

    def test_unknown_role_gives_404(self, db, admin):
        with pytest.raises(HTTPException) as e:
            rename_role("NIE_MA", RoleRename(name="Cokolwiek"), db=db, current_user=admin)
        assert e.value.status_code == 404


class TestDeleteRole:
    def test_system_role_cannot_be_deleted(self, db, admin):
        for code in (ROLE_ADMIN, ROLE_GUEST):
            with pytest.raises(HTTPException) as e:
                delete_role(code, db=db, current_user=admin)
            assert e.value.status_code == 400

    def test_role_with_users_requires_target(self, db, admin):
        db.add(User(email="t@b.pl", username="technik", hashed_password="x", role="TECHNICIAN"))
        db.commit()
        with pytest.raises(HTTPException) as e:
            delete_role("TECHNICIAN", db=db, current_user=admin)
        assert e.value.status_code == 409
        assert db.query(Role).filter(Role.code == "TECHNICIAN").first() is not None

    def test_empty_role_deletes_without_target(self, db, admin):
        delete_role("TECHNICIAN", db=db, current_user=admin)
        assert db.query(Role).filter(Role.code == "TECHNICIAN").first() is None

    def test_moves_users_and_removes_permissions(self, db, admin):
        folder = add_folder(db, "Kadry", "/Kadry")
        db.add(User(email="t@b.pl", username="technik", hashed_password="x", role="TECHNICIAN"))
        db.add(FolderPermission(folder_id=folder.id, role="TECHNICIAN", access_level=AccessLevel.WRITE))
        db.add(FolderPermission(folder_id=folder.id, role="DOCTOR", access_level=AccessLevel.READ))
        db.commit()

        result = delete_role("TECHNICIAN", reassign_to=ROLE_GUEST, db=db, current_user=admin)

        assert result["users_moved"] == 1
        assert result["permissions_removed"] == 1
        assert db.query(User).filter(User.username == "technik").first().role == ROLE_GUEST
        # uprawnienia INNEJ roli na tym samym folderze zostają nietknięte
        assert db.query(FolderPermission).filter(FolderPermission.role == "DOCTOR").count() == 1

    def test_recreated_role_does_not_inherit_old_access(self, db, admin):
        """Sedno sprawy: gdyby usunięcie zostawiało uprawnienia, rola założona
        później pod tym samym kodem po cichu odziedziczyłaby stare dostępy."""
        folder = add_folder(db, "Kadry", "/Kadry")
        db.add(FolderPermission(folder_id=folder.id, role="TECHNICIAN", access_level=AccessLevel.WRITE))
        db.commit()

        delete_role("TECHNICIAN", db=db, current_user=admin)
        odtworzona = create_role(RoleCreate(name="Technician"), db=db, current_user=admin)

        assert odtworzona.code == "TECHNICIAN"
        assert db.query(FolderPermission).filter(FolderPermission.role == "TECHNICIAN").count() == 0

    def test_cannot_move_users_into_deleted_role(self, db, admin):
        with pytest.raises(HTTPException) as e:
            delete_role("TECHNICIAN", reassign_to="TECHNICIAN", db=db, current_user=admin)
        assert e.value.status_code == 400

    def test_unknown_target_gives_404(self, db, admin):
        db.add(User(email="t@b.pl", username="technik", hashed_password="x", role="TECHNICIAN"))
        db.commit()
        with pytest.raises(HTTPException) as e:
            delete_role("TECHNICIAN", reassign_to="NIE_MA", db=db, current_user=admin)
        assert e.value.status_code == 404

    def test_non_admin_is_rejected(self, db):
        intruz = User(email="g@b.pl", username="gosc", hashed_password="x", role=ROLE_GUEST)
        with pytest.raises(HTTPException) as e:
            delete_role("TECHNICIAN", db=db, current_user=intruz)
        assert e.value.status_code == 403


class TestRoleIntegrity:
    def test_unknown_role_code_is_rejected(self, db):
        with pytest.raises(HTTPException) as e:
            ensure_role_exists(db, "NIE_MA")
        assert e.value.status_code == 400

    def test_user_with_deleted_role_sees_nothing_instead_of_crashing(self, db):
        """Wyścig: rola zniknęła, a użytkownik ma ważny token. Ma zobaczyć pustą
        listę, nie błąd 500."""
        add_folder(db, "Kadry", "/Kadry")
        sierota = User(email="s@b.pl", username="sierota", hashed_password="x", role="JUZ_NIE_MA")
        assert readable_folder_ids(sierota, db) == set()

    def test_setup_endpoint_rejects_non_admin_role(self):
        """Regresja z 2026-08-15: mechaniczna zamiana `role != UserRole.ADMIN` na
        `not X.is_admin` trafiła także w schemat pydantic, który tej własności nie
        ma — endpoint zakładania pierwszego konta zwracał 500 zamiast 400."""
        import asyncio

        from app.auth.auth import register_setup_user
        from app.schemas import UserCreate

        class PustaBaza:
            """Baza bez żadnego administratora — inaczej endpoint kończy wcześniej."""
            def query(self, *a):
                return self

            def filter(self, *a, **k):
                return self

            def all(self):
                return []

            def first(self):
                return None

        with pytest.raises(HTTPException) as e:
            asyncio.run(register_setup_user(
                UserCreate(email="a@b.pl", username="x", password="y", role=ROLE_GUEST),
                db=PustaBaza(),
            ))
        assert e.value.status_code == 400

    def test_list_reports_usage_counts(self, db, admin):
        folder = add_folder(db, "Kadry", "/Kadry")
        db.add(FolderPermission(folder_id=folder.id, role="DOCTOR", access_level=AccessLevel.READ))
        db.add(User(email="l@b.pl", username="lekarz", hashed_password="x", role="DOCTOR"))
        db.commit()

        doctor = next(r for r in list_roles(db=db, current_user=admin) if r.code == "DOCTOR")
        assert (doctor.users_count, doctor.permissions_count) == (1, 1)
