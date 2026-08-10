"""Eksport listy dokumentów do arkusza XLSX.

Po co: odpowiedź czatu typu LISTA („wypisz zarządzenia 2009") pokazuje dokumenty
na ekranie, ale pracownik i tak potrzebuje ich w Excelu — do rejestru, do przesłania
dalej, do przefiltrowania po dacie. Kopiowanie z przeglądarki gubi strukturę.

Kolumny biorą się z REJESTRU SCHEMATÓW (`doc_type_schemas.fields`), w kolejności
tam zapisanej. To celowo jedno źródło prawdy: kolejność pól widoczna w podglądzie
dokumentu jest tą samą, którą zobaczy się w arkuszu. Zmiana układu kolumn = zmiana
kolejności pól w Administracji, a nie osobny kreator eksportu.

Jeden arkusz na TYP dokumentu. Lista mieszana („dokumenty z 2009") nie ma wspólnego
zestawu pól, więc rozdzielamy ją na arkusze; lista jednorodna — najczęstszy przypadek
— daje po prostu jeden arkusz.

Wartości zapisujemy w NATYWNYCH typach Excela: data jako data, liczba jako liczba.
Bez tego sortowanie i filtrowanie w arkuszu nie działa — a to główny powód, dla
którego ktoś woli xlsx od przepisywania z ekranu.
"""

import io
import re
from datetime import date, datetime
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Excel nie przyjmuje tych znaków w nazwie arkusza ani nazw dłuższych niż 31 znaków.
_ZAKAZANE_W_NAZWIE = re.compile(r"[\[\]:*?/\\]")
MAX_NAZWA_ARKUSZA = 31

NAGLOWEK_TLO = PatternFill("solid", fgColor="F3F4F6")
NAGLOWEK_FONT = Font(bold=True)


def nazwa_arkusza(nazwa: str, zajete: set[str]) -> str:
    """Nazwa arkusza dopuszczalna dla Excela i niepowtarzalna w skoroszycie."""
    czysta = _ZAKAZANE_W_NAZWIE.sub("-", (nazwa or "Dokumenty").strip()) or "Dokumenty"
    czysta = czysta[:MAX_NAZWA_ARKUSZA]
    if czysta not in zajete:
        zajete.add(czysta)
        return czysta
    # Kolizja: dokładamy numer, przycinając nazwę tak, by zmieścić się w limicie.
    for i in range(2, 100):
        sufiks = f" ({i})"
        kandydat = czysta[: MAX_NAZWA_ARKUSZA - len(sufiks)] + sufiks
        if kandydat not in zajete:
            zajete.add(kandydat)
            return kandydat
    zajete.add(czysta)
    return czysta


def etykieta_pola(nazwa: str) -> str:
    """`osoba_podpisujaca` → `Osoba podpisujaca`.

    Rejestr trzyma nazwy techniczne (bez spacji i ogonków), bo służą też za klucze
    w danych. Do nagłówka arkusza zamieniamy je na czytelne; gdyby kiedyś doszły
    do rejestru osobne etykiety, to jedyne miejsce do zmiany.
    """
    return (nazwa or "").replace("_", " ").strip().capitalize() or "—"


def _wartosc(surowa, typ: str):
    """Wartość w typie natywnym Excela, gdy tylko da się ją rozpoznać."""
    if surowa is None or surowa == "":
        return None
    tekst = str(surowa).strip()
    if typ == "date":
        for wzor in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(tekst, wzor).date()
            except ValueError:
                continue
        return tekst                      # nierozpoznany zapis — lepiej tekst niż nic
    if typ == "number":
        try:
            liczba = float(tekst.replace(",", "."))
            return int(liczba) if liczba.is_integer() else liczba
        except ValueError:
            return tekst
    return tekst


def _typ_pola(definicja: dict) -> str:
    """`enum:a,b` traktujemy jak tekst — liczy się tylko część przed dwukropkiem."""
    return (definicja.get("type") or "string").split(":", 1)[0]


def zbuduj_xlsx(dokumenty: list[dict], schematy: dict[str, dict]) -> bytes:
    """Zbuduj skoroszyt z listy dokumentów.

    `dokumenty` — [{"filename", "doc_type", "doc_fields"}] W KOLEJNOŚCI WYŚWIETLENIA.
    Kolejność ma znaczenie: użytkownik widział listę posortowaną w konkretny sposób
    i tego samego oczekuje w arkuszu.

    `schematy` — {slug: {"name": str, "fields": [{"name","type"}, ...]}}.
    Typ spoza rejestru (albo dokument bez typu) trafia do arkusza „Pozostałe"
    z kolumnami ogólnymi — nie gubimy takich pozycji po cichu.
    """
    # Grupowanie z zachowaniem kolejności pierwszego wystąpienia typu.
    grupy: dict[str, list[dict]] = {}
    for d in dokumenty:
        slug = d.get("doc_type") or ""
        klucz = slug if slug in schematy else ""
        grupy.setdefault(klucz, []).append(d)

    wb = Workbook()
    wb.remove(wb.active)                  # domyślny pusty arkusz
    zajete: set[str] = set()

    for slug, pozycje in grupy.items():
        schemat = schematy.get(slug)
        pola = list(schemat["fields"]) if schemat else []
        tytul = schemat["name"] if schemat else "Pozostałe"
        ws = wb.create_sheet(nazwa_arkusza(tytul, zajete))

        naglowki = ["L.p."] + [etykieta_pola(p.get("name")) for p in pola] + ["Plik"]
        ws.append(naglowki)
        for komorka in ws[1]:
            komorka.font = NAGLOWEK_FONT
            komorka.fill = NAGLOWEK_TLO
            komorka.alignment = Alignment(vertical="center")

        for nr, d in enumerate(pozycje, 1):
            wartosci = d.get("doc_fields") or {}
            wiersz = [nr]
            for p in pola:
                wiersz.append(_wartosc(wartosci.get(p.get("name")), _typ_pola(p)))
            wiersz.append(d.get("filename") or "")
            ws.append(wiersz)

        # Filtr i zamrożony nagłówek — arkusz ma służyć do przeglądania rejestru,
        # a nie tylko do archiwizacji.
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(naglowki))}{ws.max_row}"

        # Szerokości kolumn z zawartości; górny limit, bo tytuły dokumentów bywają
        # bardzo długie i rozjechałyby arkusz.
        for i, _ in enumerate(naglowki, 1):
            litera = get_column_letter(i)
            najdluzsza = max(
                (len(str(k.value)) for k in ws[litera] if k.value is not None),
                default=8,
            )
            ws.column_dimensions[litera].width = min(max(najdluzsza + 2, 8), 55)
        ws.column_dimensions["A"].width = 6      # L.p. nie potrzebuje szerokości

    if not wb.sheetnames:                 # pusta lista — oddajemy czytelny, pusty arkusz
        ws = wb.create_sheet("Dokumenty")
        ws.append(["L.p.", "Plik"])

    bufor = io.BytesIO()
    wb.save(bufor)
    return bufor.getvalue()


# Polskie znaki na ASCII — do awaryjnej nazwy pliku w nagłówku HTTP.
_TRANSLITERACJA = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def naglowek_pobierania(nazwa: str) -> str:
    """Wartość nagłówka `Content-Disposition` dla nazwy z polskimi znakami.

    Nagłówki HTTP kodowane są w latin-1, więc nazwa z „ą" przewraca CAŁĄ odpowiedź
    (`UnicodeEncodeError`). Zmierzone boleśnie: pierwszy eksport zwrócił 500, choć sam
    arkusz budował się poprawnie — błąd wyszedł dopiero przy wysyłaniu nagłówka.

    Dajemy dwa warianty naraz, zgodnie z RFC 6266: `filename` z transliteracją jako
    awaryjny i `filename*` w UTF-8 dla przeglądarek, które umieją pokazać ogonki.
    """
    awaryjna = nazwa.translate(_TRANSLITERACJA).encode("ascii", "ignore").decode()
    # Sprawdzamy TRZON, nie całość: dla nazwy bez znaków ASCII zostaje samo „.xlsx",
    # co jest niepustym napisem, ale bezużyteczną nazwą pliku.
    trzon = awaryjna.rsplit(".", 1)[0] if "." in awaryjna else awaryjna
    if not trzon.strip(" -_"):
        awaryjna = "lista-dokumentow.xlsx"
    return f"attachment; filename=\"{awaryjna}\"; filename*=UTF-8''{quote(nazwa)}"


def nazwa_pliku(dokumenty: list[dict], schematy: dict[str, dict]) -> str:
    """Nazwa pobieranego pliku — po typie, gdy lista jest jednorodna."""
    typy = {d.get("doc_type") for d in dokumenty}
    dzis = date.today().isoformat()
    if len(typy) == 1:
        slug = typy.pop()
        schemat = schematy.get(slug or "")
        if schemat:
            czysty = re.sub(r"[^\w-]+", "-", schemat["name"].lower(), flags=re.UNICODE)
            return f"{czysty}-{dzis}.xlsx"
    return f"lista-dokumentow-{dzis}.xlsx"
