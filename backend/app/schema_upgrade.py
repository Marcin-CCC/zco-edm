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

# Kolacja do sortowania nazw plików — zob. `create_name_collation`.
NAME_COLLATION = "polish_natural"
_collation_ready = False


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


# Kolumny dokładane do istniejących tabel. `create_all` zakłada BRAKUJĄCE TABELE,
# ale nigdy nie dokłada kolumny do tabeli, która już jest — a obie poniższe pojawiły
# się w 1.2.0, gdy tabele stały na produkcji od miesięcy.
NEW_COLUMNS = [
    ("files", "original_filename", "varchar(500)"),
    ("doc_type_schemas", "name_pattern", "varchar(200)"),
    ("doc_type_schemas", "external", "boolean NOT NULL DEFAULT false"),
    ("users", "locale", "varchar(5)"),
]


def add_missing_columns(engine: Engine) -> None:
    """Dokłada kolumny, których nie ma. Idempotentne i bezpieczne dla starego obrazu:
    dodanie kolumny NULL-owalnej nie przeszkadza wersji, która o niej nie wie."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table, column, typ in NEW_COLUMNS:
            istnieje = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).scalar()
            if istnieje:
                continue
            logger.info("[SCHEMAT] %s: dokładam kolumnę %s %s", table, column, typ)
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {typ}"))


def create_name_collation(engine: Engine) -> None:
    """Zakłada kolację ICU do układania nazw plików.

    Po co osobna kolacja: obraz bazy stoi na Alpine, czyli na bibliotece musl, która
    NIE implementuje kolacji językowych. Mimo deklarowanego `en_US.utf8` zwykłe
    `ORDER BY` schodzi w tej bazie do porządku bajtowego (sprawdzone: `'a' < 'B'`
    zwraca fałsz). Skutki widać na liście plików: wielkie litery przed wszystkimi
    małymi, polskie znaki za całym alfabetem (`Łąka` po `zebra`), a zarządzenie
    nr 2 po nr 19. ICU jest w tym obrazie dostępne i działa niezależnie od libc.

    `kn-true` to opcja ICU „numeric ordering": ciąg cyfr porównywany jest jako
    liczba, a nie znak po znaku — dzięki temu `2_2025` stoi przed `10_2025`.

    Idempotentne i bezpieczne dla poprzedniego obrazu: kolacja to nowy obiekt,
    którego stary kod nie używa, więc cofnięcie wdrożenia niczego nie psuje.
    Nieudane założenie NIE jest błędem krytycznym — flaga zostaje fałszywa,
    a lista plików wraca do zwykłego `ORDER BY`: kolejność gorsza, ale działa.
    """
    global _collation_ready
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        istnieje = conn.execute(
            text("SELECT 1 FROM pg_collation WHERE collname = :n"),
            {"n": NAME_COLLATION},
        ).scalar()
        if not istnieje:
            logger.info("[SCHEMAT] Zakładam kolację %s (ICU pl-PL + liczby)", NAME_COLLATION)
            conn.execute(text(
                f'CREATE COLLATION "{NAME_COLLATION}" '
                "(provider = icu, locale = 'pl-PL-u-kn-true')"
            ))
    _collation_ready = True


def name_collation_available() -> bool:
    """Czy `NAME_COLLATION` jest gotowa do użycia w `ORDER BY`.

    Ustalane raz, przy starcie. Poza Postgresem (testy na SQLite) zostaje fałsz.
    """
    return _collation_ready


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
        add_missing_columns(engine)
        with Session(engine) as session:
            seed_roles(session)
        # Osobna klamra: brak ICU w bazie ma tylko pogorszyć kolejność na liście
        # plików, a nie unieważnić uaktualnień wykonanych powyżej.
        try:
            create_name_collation(engine)
        except Exception:
            logger.exception("[SCHEMAT] Kolacja nazw niedostępna — sortowanie bajtowe")
    except Exception:
        # Aplikacja ma wstać nawet wtedy, gdy uaktualnienie się nie powiedzie —
        # inaczej jeden błąd w migracji odcina użytkowników od wszystkiego.
        # Ślad w logu wystarczy: bez słownika ról interfejs zarządzania rolami
        # będzie pusty, ale logowanie i dostęp do plików działają dalej.
        logger.exception("[SCHEMAT] Uaktualnienie startowe nie powiodło się")
