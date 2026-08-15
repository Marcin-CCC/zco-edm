"""Uaktualnienia schematu i słowników wykonywane raz, przy starcie aplikacji.

Projekt nie ma Alembica: tabele powstają przez ``Base.metadata.create_all``, które
zakłada BRAKUJĄCE tabele, ale nie rusza kolumn w istniejących. Wszystko, czego
``create_all`` nie potrafi, musi więc zrobić ten moduł — idempotentnie, bo wykonuje
się przy każdym starcie kontenera, na obu instancjach (ZCO i HiRS).

Zasada: nic tutaj nie może zmieniać DANYCH w sposób, którego nie zrozumie poprzednia
wersja aplikacji. Cofnięcie wdrożenia to podmiana tagu obrazu — schemat zostaje taki,
jaki był po migracji, więc stary obraz musi umieć na nim wystartować.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import BUILT_IN_ROLES, Role

logger = logging.getLogger(__name__)

# Kolumny trzymające kod roli. Do 1.0.21 były natywnym typem `userrole` Postgresa.
ROLE_COLUMNS = [("users", "role"), ("folder_permissions", "role")]


def convert_role_columns_to_text(engine: Engine) -> None:
    """Zamienia kolumny z rolą z natywnego enuma ``userrole`` na ``varchar(50)``.

    Po co: z typu enum w Postgresie nie da się usunąć wartości (``ALTER TYPE`` zna
    tylko ``ADD VALUE``), więc dopóki rola jest enumem, usunięcie roli zostawia
    martwą etykietę w schemacie na zawsze, a dodanie wymaga DDL-a w środku obsługi
    żądania HTTP.

    WARTOŚCI POZOSTAJĄ NIETKNIĘTE (``USING role::text``): "ADMIN" zostaje "ADMIN".
    To celowe — dzięki temu obraz w poprzedniej wersji, który czyta rolę jako enum
    Pythona po NAZWIE elementu, działa na zmigrowanym schemacie tak samo jak przed
    migracją. Z tego samego powodu NIE kasujemy osieroconego typu ``userrole``.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        for table, column in ROLE_COLUMNS:
            typ = conn.execute(
                text(
                    "SELECT udt_name FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).scalar()
            if typ is None or typ.startswith("varchar"):
                continue
            logger.info("[SCHEMAT] %s.%s: %s -> varchar(50)", table, column, typ)
            conn.execute(
                text(
                    f"ALTER TABLE {table} ALTER COLUMN {column} "
                    f"TYPE varchar(50) USING {column}::text"
                )
            )


def seed_roles(session: Session) -> None:
    """Uzupełnia słownik ról: role wbudowane oraz kody zastane w danych.

    Drugi człon nie jest ostrożnością na wyrost. Instancja mogła dostać rolę spoza
    naszej listy (ręczny wpis, starsze wdrożenie); gdyby taki kod nie trafił do
    słownika, rola zniknęłaby z interfejsu, mimo że użytkownicy nadal ją mają —
    a więc administrator nie miałby jak nią zarządzać ani jej usunąć.
    """
    known = {r.code for r in session.query(Role.code).all()}

    for item in BUILT_IN_ROLES:
        if item["code"] not in known:
            session.add(Role(**item))
            known.add(item["code"])

    inspector = inspect(session.get_bind())
    tables = set(inspector.get_table_names())
    for table, column in ROLE_COLUMNS:
        if table not in tables:
            continue
        used = session.execute(
            text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")
        ).scalars().all()
        for code in used:
            if code in known:
                continue
            logger.warning("[SCHEMAT] Rola %r zastana w %s — dopisana do słownika", code, table)
            session.add(Role(code=code, name=code, is_system=False, sort_order=900))
            known.add(code)

    session.commit()


def run_startup_upgrades(engine: Engine) -> None:
    """Wywoływane raz przy starcie, po ``create_all``."""
    try:
        convert_role_columns_to_text(engine)
        with Session(engine) as session:
            seed_roles(session)
    except Exception:
        # Aplikacja ma wstać nawet wtedy, gdy uaktualnienie się nie powiedzie —
        # inaczej jeden błąd w migracji odcina użytkowników od wszystkiego.
        # Ślad w logu wystarczy: bez słownika ról interfejs zarządzania rolami
        # będzie pusty, ale logowanie i dostęp do plików działają dalej.
        logger.exception("[SCHEMAT] Uaktualnienie startowe nie powiodło się")
