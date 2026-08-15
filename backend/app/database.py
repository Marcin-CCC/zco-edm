from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import (
    assert_environment_is_consistent,
    assert_secret_key_is_safe,
    settings,
)

# Bezpiecznik stoi TUTAJ, a nie w `main.py`, bo to jest jedyne przejście do bazy.
# Chroni więc także skrypty pomocnicze (backfille, pomiary), które uruchamia się
# z konsoli — a to właśnie one najłatwiej odpalić z pomyłkowym adresem bazy.
assert_environment_is_consistent(settings.APP_ENV, settings.DATABASE_URL)
assert_secret_key_is_safe(settings.APP_ENV, settings.SECRET_KEY)


class Base(DeclarativeBase):
    """Baza dla wszystkich modeli SQLAlchemy."""
    pass


engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency wstrzykujaca sesje bazy danych."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()