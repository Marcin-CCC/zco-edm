from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


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