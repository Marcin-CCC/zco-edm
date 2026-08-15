"""Bezpiecznik: kod deweloperski nie może dotknąć zdalnej bazy.

Uruchom: pytest backend/tests/test_environment_guard.py -v

Test istnieje z powodu konkretnego zdarzenia (2026-08-15): kontener deweloperski
z zamontowanym kodem z dysku i adresem bazy wskazującym Sparka wstał razem
z Dockerem i wykonał migrację schematu na bazie klienta. Nikt tego nie zlecił.
"""
import pytest

from app.config import assert_environment_is_consistent, assert_secret_key_is_safe

SPARK = "postgresql+psycopg2://postgres:x@192.168.1.34:5433/edmdatabase"


class TestLocalDatabaseIsAlwaysAllowed:
    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "host.docker.internal"])
    def test_dev_may_use_local_database(self, host):
        assert_environment_is_consistent("dev", f"postgresql+psycopg2://u:p@{host}:15432/edmdatabase")

    def test_url_without_host_passes(self):
        """sqlite w testach jednostkowych nie ma hosta — nie ma czego chronić."""
        assert_environment_is_consistent("dev", "sqlite://")


class TestRemoteDatabaseNeedsProduction:
    def test_dev_pointing_at_spark_refuses_to_start(self):
        with pytest.raises(RuntimeError) as e:
            assert_environment_is_consistent("dev", SPARK)
        komunikat = str(e.value)
        # Komunikat ma powiedzieć CO jest nie tak i JAK to naprawić — inaczej
        # pierwszym odruchem będzie obejście bezpiecznika, a nie poprawka.
        assert "192.168.1.34" in komunikat
        assert "APP_ENV=production" in komunikat
        assert "DATABASE_URL" in komunikat

    def test_production_may_use_remote_database(self):
        assert_environment_is_consistent("production", SPARK)

    @pytest.mark.parametrize("app_env", ["", "prod", "Production", "test"])
    def test_only_exact_production_unlocks_remote(self, app_env):
        """Literówka w wartości nie może otwierać dostępu do produkcyjnej bazy."""
        with pytest.raises(RuntimeError):
            assert_environment_is_consistent(app_env, SPARK)


class TestSecretKeyGuard:
    """Klucz podpisujący tokeny sesji. Wartość domyślna z repozytorium oznacza,
    że każdy, kto widział repozytorium, może wystawić sobie token administratora."""

    @pytest.mark.parametrize("placeholder", [
        "zco-edm-secret-key-change-in-production",
        "hirs-demo-secret-change-me",
        "",
        "za-krotki-klucz",
    ])
    def test_production_refuses_placeholder_or_short_key(self, placeholder):
        with pytest.raises(RuntimeError) as e:
            assert_secret_key_is_safe("production", placeholder)
        assert "SECRET_KEY" in str(e.value)

    def test_production_accepts_a_real_key(self):
        assert_secret_key_is_safe("production", "k" * 32)

    def test_dev_is_not_blocked_by_the_default(self):
        """Lokalnie domyślka jest w porządku — nikt się do tego nie dobierze,
        a wymuszanie sekretu w dev tylko zachęca do obchodzenia bezpiecznika."""
        assert_secret_key_is_safe("dev", "zco-edm-secret-key-change-in-production")

