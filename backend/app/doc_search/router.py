"""Wyszukiwanie po polach strukturalnych dokumentów (#7B-2).

Parsowanie zapisuje w `files.metadata_` typ dokumentu i wartości pól nagłówkowych:
    metadata_ = { ..., "doc_type": "zarzadzenie",
                  "doc_fields": {"data": "2023-04-07", "numer_dokumentu": "8/2023"} }

Dwa wejścia:
- POST ""     — filtr STRUKTURALNY (typ + warunki na polach) z formularza.
- POST "/nl"  — pytanie po polsku → LLM zamienia je na ten sam filtr (NL→filtr).

Oba używają tej samej logiki SQL (`_run_search`) po JSON w Postgresie i tego samego
RBAC-u roli (użytkownik widzi tylko dokumenty z dozwolonych folderów).
"""
import calendar
import json
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.auth import get_current_user
from app.models import User, File as FileModel
from app.rbac import readable_folder_ids
from app.config import settings
from app.doc_schemas.router import get_active_schemas

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/doc-search", tags=["DocSearch"])

_ALLOWED_OPS = {"eq", "contains", "gte", "lte", "gt", "lt"}
_NL_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

_YEAR_RE = re.compile(r"^\d{4}$")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{1,2}$")


def _expand_date_bound(value: str, op: str) -> str:
    """Rozwiń „rok" / „rok-miesiąc" do pełnej daty granicznej.

    Porównania idą po TEKŚCIE, więc `data <= '2023'` nie łapie '2023-04-07'
    (dłuższy napis o tym samym prefiksie jest większy) — przez to pytania
    „w roku 2023" dawały 0 wyników. Rozwijamy więc granicę okresu, zależnie
    od tego, czy operator sięga jego POCZĄTKU czy KOŃCA:

      gte 2023 (od 2023)    → 2023-01-01     lt  2023 (przed 2023) → 2023-01-01
      lte 2023 (do 2023)    → 2023-12-31     gt  2023 (po 2023)    → 2023-12-31

    Dzięki temu „od 2024" obejmuje rok 2024, a „po 2024" już nie.
    Wartości pełnych dat zostawiamy bez zmian.
    """
    # gte/lt sięgają POCZĄTKU okresu, lte/gt jego KOŃCA
    to_start = op in ("gte", "lt")

    if _YEAR_RE.match(value):
        return f"{value}-01-01" if to_start else f"{value}-12-31"
    if _YEAR_MONTH_RE.match(value):
        year, month = value.split("-")
        month_i = int(month)
        if not 1 <= month_i <= 12:
            return value
        norm = f"{int(year):04d}-{month_i:02d}"
        if to_start:
            return f"{norm}-01"
        return f"{norm}-{calendar.monthrange(int(year), month_i)[1]:02d}"
    return value


class FieldFilter(BaseModel):
    field: str
    op: str = "contains"          # eq | contains | gte | lte
    value: str


# Pola identyfikujące osobę — warunek na nich jest WIARYGODNY: skoro nic nie pasuje,
# takich dokumentów naprawdę nie ma. Doklejanie odpowiedzi z treści byłoby tu szkodliwe
# (mierzone wcześniej: model dopasowywał listę do fałszywego założenia pytania).
_POLA_OSOBOWE = ("nazwisko", "osoba", "opracowal", "sprawdzil", "zatwierdzil", "podpisal",
                 "organwydajacy", "dyrektor", "kierownik", "autor", "wydal")


_SLOWA_OGOLNE = {"dokument", "dokumenty", "dokumentow", "dokumentów", "plik", "pliki",
                 "plikow", "plików", "akta", "wszystko", "wszystkie", "wszystkich",
                 "lista", "liste", "listę", "spis", "zestawienie", "pokaz", "pokaż",
                 "wypisz", "wylistuj", "znajdz", "znajdź", "podaj", "daj", "ile", "jest",
                 "sa", "są", "jakie", "w", "z", "ze", "na", "do", "systemie", "bazie"}


# Słowa, które określają RELACJĘ do poprzedniej odpowiedzi, a nie treść dokumentu.
# Model potrafi zrobić z nich warunek na polu („a inne wnioski" → tytuł zawiera „inne"),
# co daje zero wyników i pytanie ląduje w ślepej gałęzi.
_KWANTYFIKATORY = {"inne", "inny", "inna", "innych", "pozostale", "pozostałe", "jeszcze",
                   "kolejne", "kolejny", "nastepne", "następne", "nowe", "nowszy", "nowsze",
                   "wszystkie", "wszystkich", "jakies", "jakieś", "reszta", "reszte", "resztę"}


def wartosc_bez_tresci(value: str) -> bool:
    """Czy wartość warunku to samo słowo relacyjne („inne", „pozostałe")."""
    return (value or "").strip().lower() in _KWANTYFIKATORY


def zapytanie_ogolnikowe(query: str) -> bool:
    """Czy wypowiedź nie nazywa NICZEGO konkretnego (same słowa ogólne i polecenia).

    „pokaż wszystkie dokumenty" → True (prosimy o doprecyzowanie zamiast wypisywać bazę).
    „polecenie wyjazdu służbowego" → False (nazwa konkretnego dokumentu).
    """
    slowa = [s.strip(".,;:!?\"'()") for s in (query or "").lower().split()]
    return not any(s and s not in _SLOWA_OGOLNE for s in slowa)


def warunek_frazowy(field: str, op: str, value: str) -> bool:
    """Czy warunek jest NIEPEWNYM dopasowaniem frazy (a nie identyfikatorem/datą/osobą).

    Rozstrzyga, co zrobić, gdy wyszukiwanie po polach nic nie znalazło. Warunek na
    numerze, dacie albo osobie jest wiarygodny — zero wyników znaczy „nie ma takich
    dokumentów" i mówimy to wprost. Warunek na frazie opisowej (tytuł, temat) jest
    niepewny: nawet z dopasowaniem po rdzeniach potrafi nie trafić w sformułowanie
    użyte w dokumencie, więc wtedy warto jeszcze poszukać w treści.
    """
    from app.doc_extract import _norm_key
    if (op or "").lower() != "contains":
        return False                                  # zakresy dat i eq = precyzyjne
    if any(z.isdigit() for z in value or ""):
        return False                                  # numer, rok, sygnatura
    nazwa = _norm_key(field)
    return not any(k in nazwa for k in _POLA_OSOBOWE)


class SearchRequest(BaseModel):
    doc_type: Optional[str] = None
    filters: list[FieldFilter] = []
    limit: int = 100


class NLSearchRequest(BaseModel):
    query: str
    limit: int = 100


class SearchHit(BaseModel):
    id: int
    filename: str
    folder_id: Optional[int] = None
    doc_type: Optional[str] = None
    fields: dict = {}


DLUGOSC_RDZENIA = 4      # „urlop opiekuńczy" → urlo, opie (łapie „urlopu opiekuńczego")
_STOPY = {"o", "w", "na", "do", "za", "z", "ze", "i", "oraz", "dla", "od", "po", "przez", "nr"}


def rdzenie(fraza: str) -> list[str]:
    """Rozłóż frazę na rdzenie wyrazów, po których wolno szukać.

    Dopasowanie po całej frazie zawodzi na polskiej odmianie: warunek
    `tytul zawiera "urlop opiekuńczy"` NIE trafia w „Wniosek o udzielenie urlopu
    opiekuńczego", bo to porównanie dosłowne. Skracamy więc każde słowo do rdzenia
    i wymagamy obecności wszystkich rdzeni (AND).

    Zmierzone na haśle „karta odmowy przyjęcia": przy rdzeniu 5- i 6-znakowym wynik
    to ZERO trafień („karta" nie zawiera się w „karty"), przy 4 — trzy właściwe
    dokumenty. Wyrazy z cyframi („30/2024") zostawiamy nietknięte, żeby nie zlewać
    numerów z różnych lat.
    """
    out: list[str] = []
    for slowo in fraza.lower().replace(",", " ").replace(";", " ").split():
        if slowo in _STOPY:
            continue
        if any(z.isdigit() for z in slowo):
            out.append(slowo)                       # numery i daty bez skracania
        elif len(slowo) > DLUGOSC_RDZENIA:
            out.append(slowo[:DLUGOSC_RDZENIA])
        elif len(slowo) >= 3:
            out.append(slowo)
    return out


def _zawiera_rdzenie(col, val: str):
    """Warunek: kolumna zawiera WSZYSTKIE rdzenie frazy (odporne na odmianę)."""
    czesci = rdzenie(val)
    if not czesci:
        return col.ilike(f"%{val}%")
    warunki = [col.ilike(f"%{r}%") for r in czesci]
    return and_(*warunki) if len(warunki) > 1 else warunki[0]


def _field_condition(field: str, op: str, val: str):
    """Warunek SQL na jednym polu z `metadata->doc_fields`."""
    col = FileModel.metadata_.op("->")("doc_fields").op("->>")(field)
    if op == "eq":
        return func.lower(col) == val.lower()
    if op == "contains":
        # Rdzenie WYŁĄCZNIE dla fraz opisowych. Na nazwisku byłyby błędem: „Kowalska"
        # skrócona do „kowa" łapie „Jan Kowalski" — zmierzone 10 fałszywych trafień
        # na wzorach formularzy z przykładowym nazwiskiem. Osoby dopasowujemy dosłownie
        # (mianownik zapewnia już warstwa NL→filtr).
        if warunek_frazowy(field, op, val):
            return _zawiera_rdzenie(col, val)
        return col.ilike(f"%{val}%")
    if op == "gte":
        return col >= _expand_date_bound(val, "gte")
    if op == "lte":
        return col <= _expand_date_bound(val, "lte")
    if op == "gt":     # „po 2024" — rok 2024 NIE wchodzi
        return col > _expand_date_bound(val, "gt")
    if op == "lt":     # „przed 2024" — rok 2024 NIE wchodzi
        return col < _expand_date_bound(val, "lt")
    return None


def _run_search(
    db: Session,
    current_user: User,
    doc_type: Optional[str],
    filters: list[FieldFilter],
    limit: int = 100,
) -> list[SearchHit]:
    """Wspólna logika: filtr strukturalny → SQL po metadata_ + RBAC roli.

    UWAGA co do łączenia warunków: warunki o RÓŻNYCH parametrach (np. dostawca=X
    oraz kwota>1000) łączymy przez AND, ale ten SAM warunek rozłożony na różne
    nazwy pól (np. „po 2024" dla typu nieokreślonego → data, data_wydania,
    data_podpisania…) łączymy przez OR. Bez tego pytanie „dokumenty po 2024"
    wymagałoby, by jeden dokument miał JEDNOCZEŚNIE wszystkie te pola — czyli
    zawsze zero wyników.
    """
    # Brak filtra po metadata_ IS NOT NULL: pliki bez metadanych (sparsowane przed
    # wdrożeniem klasyfikacji) też mają się pokazywać, gdy nie ma warunków na polach.
    q = db.query(FileModel)

    # Typ dokumentu (metadata->>'doc_type'). Kolumna to generic JSON (nie JSONB),
    # więc `.astext` nie działa — używamy operatorów PostgreSQL ->/->> przez .op().
    if doc_type:
        q = q.filter(FileModel.metadata_.op("->>")("doc_type") == doc_type.strip())

    # Grupuj warunki po (operator, wartość); różne pola w grupie → OR
    groups: dict[tuple[str, str], list[str]] = {}
    for f in filters:
        op = (f.op or "contains").lower()
        field = (f.field or "").strip()
        if op not in _ALLOWED_OPS or not field:
            continue
        key = (op, (f.value or "").strip())
        fields = groups.setdefault(key, [])
        if field not in fields:          # odsiej duplikaty (model bywa gadatliwy)
            fields.append(field)

    for (op, val), fields in groups.items():
        conds = [c for c in (_field_condition(fl, op, val) for fl in fields) if c is not None]
        # Nazwa pliku jako dodatkowy cel dopasowania fraz. Pole `tytul` ma wypełnione
        # tylko 46 ze 157 dokumentów, a nazwa pliku bywa dokładnie tym, czego użytkownik
        # szuka („wniosek o urlop opiekuńczy.docx"). Tylko dla fraz opisowych: nazwisko
        # w nazwie pliku prawie nie występuje, a data i numer mają własne pola.
        if any(warunek_frazowy(fl, op, val) for fl in fields):
            conds.append(_zawiera_rdzenie(FileModel.filename, val))
        if not conds:
            continue
        q = q.filter(or_(*conds) if len(conds) > 1 else conds[0])

    # RBAC: tylko foldery czytelne dla roli (admin: readable is None → bez filtra)
    readable = readable_folder_ids(current_user, db)
    if readable is not None:
        if not readable:
            return []
        q = q.filter(FileModel.folder_id.in_(sorted(readable)))

    limit = min(max(limit, 1), 500)
    files = q.order_by(FileModel.id.desc()).limit(limit).all()

    hits = []
    for f in files:
        meta = f.metadata_ or {}
        hits.append(SearchHit(
            id=f.id,
            filename=f.filename,
            folder_id=f.folder_id,
            doc_type=meta.get("doc_type"),
            fields=meta.get("doc_fields") or {},
        ))
    return hits


@router.post("", response_model=list[SearchHit])
def search_documents(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Znajdź dokumenty po typie i wartościach pól (filtr strukturalny z formularza)."""
    for f in payload.filters:
        if (f.op or "contains").lower() not in _ALLOWED_OPS:
            raise HTTPException(status_code=400, detail=f"Nieobsługiwany operator: {f.op}")
    return _run_search(db, current_user, payload.doc_type, payload.filters, payload.limit)


# ==================== NL → filtr ====================
def _nl_response_format(schemas: list[dict]) -> dict:
    slugs = [s["slug"] for s in schemas] + [""]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "filtr_wyszukiwania",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "doc_type": {"type": "string", "enum": slugs},
                    # Typ nazwany w pytaniu — także wtedy, gdy nie ma go w katalogu.
                    # Dzięki temu odróżniamy „wypisz dokumenty" (brak typu) od „ile jest
                    # umów?" (typ podany, ale nieznany) — w drugim przypadku nie wolno
                    # zwrócić wszystkiego.
                    "typ_z_pytania": {"type": "string"},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "field": {"type": "string"},
                                "op": {
                                    "type": "string",
                                    "enum": ["eq", "contains", "gte", "lte", "gt", "lt"],
                                },
                                "value": {"type": "string"},
                            },
                            "required": ["field", "op", "value"],
                        },
                    },
                },
                "required": ["doc_type", "typ_z_pytania", "filters"],
            },
        },
    }


async def _nl_to_filter(query: str, schemas: list[dict]) -> dict:
    """Zamień pytanie po polsku na filtr {doc_type, filters[]} (LLM, guided decoding)."""
    lines = ["KATALOG TYPÓW DOKUMENTÓW:"]
    for s in schemas:
        fields = ", ".join(f.get("name") for f in (s.get("fields") or [])) or "—"
        lines.append(f"- slug: {s['slug']} | nazwa: {s.get('name', s['slug'])} | pola: {fields}")
    catalog = "\n".join(lines)
    system = (
        "Zamieniasz pytanie użytkownika na filtr wyszukiwania dokumentów. Masz katalog "
        "typów i ich pól. Ustaw doc_type (slug) TYLKO jeśli pytanie wyraźnie wskazuje typ "
        "OBECNY w katalogu; w przeciwnym razie doc_type=\"\".\n"
        "typ_z_pytania: nazwa rodzaju dokumentu, o który pyta użytkownik, w mianowniku "
        "liczby pojedynczej (np. umowa, faktura, zarządzenie) — wypełnij TAKŻE wtedy, gdy "
        "tego rodzaju NIE MA w katalogu. Zostaw pusty string, gdy pytanie nie wskazuje "
        "rodzaju albo używa ogólnych słów (dokumenty, pliki, akta).\n"
        "Dodaj warunki na polach (nazwa pola DOKŁADNIE z "
        "katalogu wybranego typu, operator, wartość).\n"
        "OPERATORY — rozróżniaj włączające od wyłączających:\n"
        "  eq       = równe dokładnie\n"
        "  contains = zawiera\n"
        "  gte      = OD danego roku/daty WŁĄCZNIE (np. 'od 2024', 'począwszy od 2024', "
        "'2024 i później')\n"
        "  lte      = DO danego roku/daty WŁĄCZNIE (np. 'do 2024', 'najpóźniej 2024')\n"
        "  gt       = PO danym roku/dacie, BEZ NIEGO (np. 'po 2024', 'późniejsze niż 2024', "
        "'nowsze niż 2024')\n"
        "  lt       = PRZED danym rokiem/datą, BEZ NIEGO (np. 'przed 2024', 'sprzed 2024', "
        "'wcześniejsze niż 2024', 'starsze niż 2024')\n"
        "Dla przedziału 'w latach 2023-2026' użyj gte 2023 oraz lte 2026. Dla 'w 2023 roku' "
        "użyj gte 2023 oraz lte 2023.\n"
        "WARTOŚCI:\n"
        "  - Daty i lata podawaj jako tekst (np. 2023 albo 2023-04).\n"
        "  - Nazwiska, nazwy i frazy podawaj w formie PODSTAWOWEJ (mianownik), nie w tej "
        "odmienionej z pytania: 'podpisane przez Sikorskiego' → wartość 'Sikorski'; "
        "'zarządzenia dyrektora Kowalskiego' → 'Kowalski'; 'umowy z Polmedi' → 'Polmedi'.\n"
        "  - Dla nazwisk, nazw i fragmentów tekstu używaj operatora contains, bo pole zawiera "
        "zwykle pełniejszą wartość (np. w polu jest 'Adrian Sikorski', a pytanie mówi tylko "
        "'Sikorski'). Operatora eq używaj WYŁĄCZNIE do dokładnych identyfikatorów, np. numeru "
        "dokumentu '30/2024' albo wartości ze słownika.\n"
        "Nie wymyślaj pól spoza katalogu. Zwróć wyłącznie JSON zgodny ze schematem."
    )
    body = {
        "model": settings.VLLM_MODEL,
        "temperature": 0,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{catalog}\n\nPYTANIE: {query}"},
        ],
        "response_format": _nl_response_format(schemas),
    }
    url = f"{settings.VLLM_URL.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_NL_TIMEOUT) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


@router.post("/nl")
async def nl_search(
    payload: NLSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pytanie po polsku → filtr (LLM) → wyszukiwanie. Zwraca rozpoznany filtr + wyniki."""
    schemas = get_active_schemas(db)
    if not (payload.query or "").strip():
        raise HTTPException(status_code=400, detail="Puste zapytanie.")

    try:
        parsed = await _nl_to_filter(payload.query.strip(), schemas)
    except Exception as e:
        logger.warning(f"[DOC-SEARCH-NL] Rozpoznanie filtra nieudane: {e}")
        raise HTTPException(status_code=502, detail="Nie udało się zrozumieć zapytania.")

    valid_slugs = {s["slug"] for s in schemas}
    doc_type = (parsed.get("doc_type") or "").strip() or None
    if doc_type and doc_type not in valid_slugs:
        doc_type = None

    # Pytanie wskazuje rodzaj dokumentu, którego NIE MA w rejestrze (np. „ile jest umów?")
    # → nie wolno zwrócić wszystkiego. Mówimy wprost, że takiego typu nie znamy.
    asked_type = (parsed.get("typ_z_pytania") or "").strip()
    if asked_type and not doc_type:
        known = {s["slug"] for s in schemas} | {(s.get("name") or "").lower() for s in schemas}
        if asked_type.lower() not in known:
            logger.info(f"[DOC-SEARCH-NL] Nieznany typ w pytaniu: {asked_type!r}")
            return {
                "filter": {"doc_type": None, "filters": []},
                "hits": [],
                "unknown_type": asked_type,
                "known_types": sorted(s.get("name") or s["slug"] for s in schemas),
            }

    # Pola dozwolone (odsiej wymyślone przez model): dla wybranego typu — jego pola,
    # dla typu nieokreślonego — suma pól ze WSZYSTKICH aktywnych schematów.
    # Dopasowujemy w postaci kanonicznej, bo model zapisuje nazwy po swojemu
    # („kod procedury" → „kod_procedury", „opracował" → „opracowal”), a filtr musi
    # trafić w nazwę Z REJESTRU — inaczej warunek przepadłby po cichu.
    from app.doc_extract import _norm_key
    zrodla = [s for s in schemas if not doc_type or s["slug"] == doc_type]
    allowed_by_norm = {
        _norm_key(f.get("name")): f.get("name")
        for s in zrodla for f in (s.get("fields") or []) if f.get("name")
    }

    filters: list[FieldFilter] = []
    seen: set[tuple[str, str, str]] = set()
    for f in (parsed.get("filters") or []):
        field = (f.get("field") or "").strip()
        value = (f.get("value") or "").strip()
        op = (f.get("op") or "contains").lower()
        if not field or not value:
            continue
        if wartosc_bez_tresci(value):
            logger.info(f"[DOC-SEARCH-NL] Pominięto warunek bez treści: {field}={value!r}")
            continue
        if op not in _ALLOWED_OPS:
            op = "contains"
        canon = allowed_by_norm.get(_norm_key(field))
        if allowed_by_norm and not canon:
            logger.info(f"[DOC-SEARCH-NL] Pominięto pole spoza rejestru: {field!r}")
            continue
        field = canon or field
        # Model bywa gadatliwy i powtarza ten sam warunek — pokazujemy go raz
        # (samo wyszukiwanie i tak scala duplikaty, ale w formularzu tylko mylą).
        key = (field, op, value)
        if key in seen:
            continue
        seen.add(key)
        filters.append(FieldFilter(field=field, op=op, value=value))

    # Brak jakiegokolwiek kryterium (ani typu, ani warunku) = nie wiadomo, o które
    # dokumenty chodzi. Wyszukiwanie bez warunków zwróciłoby CAŁĄ bazę i udawało
    # odpowiedź — tak samo mylące jak nieznany typ dokumentu, który odsiewamy wyżej.
    if not doc_type and not filters:
        logger.info(f"[DOC-SEARCH-NL] Brak kryteriów w pytaniu: {payload.query[:70]!r}")
        return {
            "filter": {"doc_type": None, "filters": []},
            "hits": [],
            "no_criteria": True,
            # Czy wypowiedź jest OGÓLNIKOWA („pokaż wszystkie dokumenty"), czy nazywa
            # coś konkretnego („polecenie wyjazdu służbowego" — nazwa dokumentu, której
            # rejestr nie umiał zamienić na warunek). W pierwszym przypadku prosimy o
            # doprecyzowanie, w drugim lepiej poszukać w treści niż odsyłać z niczym.
            "generic_query": zapytanie_ogolnikowe(payload.query),
        }

    hits = _run_search(db, current_user, doc_type, filters, payload.limit)
    return {
        "filter": {"doc_type": doc_type, "filters": [f.model_dump() for f in filters]},
        "hits": [h.model_dump() for h in hits],
        # Czy wśród warunków jest niepewne dopasowanie frazy — frontend decyduje na tej
        # podstawie, czy przy zerze wyników dokleić odpowiedź z treści dokumentów.
        "phrase_filter": any(warunek_frazowy(f.field, f.op, f.value) for f in filters),
    }
