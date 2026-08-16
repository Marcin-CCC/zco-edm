"""Dobór fragmentów z dokumentu-zwycięzcy — pytania o złożonym ciągu rozumowania.

Problem (zmierzone na bazie ZCO, rozmowa 1297–1308): pracownik pyta „w jakim wieku
dzieci mogą korzystać z wczasów pod gruszą?". Odpowiedź wymaga połączenia dwóch
miejsc regulaminu: „wczasy pod gruszą" są jednym z celów ZFŚS, a wiek dzieci jest
określony raz, dla całego Funduszu. Wyszukiwanie wektorowe tego nie przeskoczy —
fragment o gruszy nie zawiera słowa „wiek", a fragment o wieku nie zawiera słowa
„grusza". Zmierzony ranking dla tego pytania:

    poz.  1–6   0,60–0,52   Regulamin ZFŚS — fragmenty o gruszy, BEZ wieku
    poz. 10–14  0,48–0,46   polisy — wiek dziecka, ale w ubezpieczeniu NW
    poz.   64   0,411       Regulamin ZFŚS — JEDYNY fragment z wiekiem 5–18 lat

Model dostał kontekst bez odpowiedzi i oparł się na jedynym fragmencie mówiącym
o wieku dziecka — z polisy. Podniesienie topK nie pomaga: właściwy fragment leży
poniżej pasma przyjętych (próg 0,50), więc weszłoby przed nim ~60 gorszych.

Rozwiązanie opiera się na obserwacji z pomiaru: DOKUMENT jest rozpoznawany
bezbłędnie (6 z 6 czołowych trafień to ten regulamin), myli się tylko STRONA.
Wystarczy więc dobrać z dokumentu-zwycięzcy fragmenty pod tę część pytania,
której czołowe trafienia NIE POKRYWAJĄ („wieku") — reszta pytania jest już
załatwiona i tylko przyciąga do tych samych stron.

Zapytanie uzupełniające = niepokryte słowa + TYTUŁ dokumentu. Tytuł jest tu
konieczny, nie ozdobny — zmierzone pozycje właściwego fragmentu w obrębie pliku:

    „wieku Zarządzenie i Regulamin ZFŚS"   → pozycja 3   ✔
    „wieku"                                → poza pierwszą piątką
    „wieku dzieci"                         → poza pierwszą piątką
    całe pytanie                           → poza pierwszą piątką

Tytuł zakotwicza zapytanie w języku przepisów ogólnych, a właśnie tam (a nie przy
opisie świadczenia) regulaminy zapisują kryteria uprawnień.

WYBIÓRCZOŚĆ. Mechanizm ma nie ruszać pytań, które już działają. Zmierzone na
sześciu pytaniach: odpalił się WYŁĄCZNIE na wadliwym; „jak rozliczyć delegację?",
„w jakim wieku dzieci uprawnione są do ZFŚS?" i „na co mogą iść środki z ZFŚS?"
nie mają niepokrytej reszty (odpowiedź już jest w kontekście), a „ile wynosi dieta
za delegację?" i pytanie o temat spoza bazy nie mają ani jednego fragmentu nad
progiem. Ten ostatni warunek jest najważniejszy: gdy kontekst jest pusty, odmowa
jest POPRAWNA i doboru nie robimy — inaczej ratowalibyśmy odpowiedzi, których
w dokumentach nie ma.

O TYM, CO WCHODZI DO KONTEKSTU, DECYDUJE WOŁAJĄCY — i to nie jest szczegół.
Pierwsza wersja sama odsiewała fragmenty po progu 0,50, przez co nie działała
na najczęstszej ścieżce produkcyjnej. Zmierzone na żywym zapytaniu: pytanie
o wczasy pod gruszą uruchamia zawężenie leksykalne (`terminy=['dzieci','gruszą']`
w app/chat/lexical.py), a wtedy próg w n8n jest WYŁĄCZONY i do kontekstu wchodzi
całe piętnaście fragmentów. Moduł musi więc dostać dokładnie tę listę, którą
zobaczy model — inaczej liczy niepokrytą resztę z innego zbioru niż faktyczny.
(Na szczęście wynik wyszedł ten sam: ani jeden z 15 fragmentów nie zawiera słowa
„wieku", więc reszta to nadal ['wieku'], a zwycięzcą jest ten sam regulamin.)

Zapytanie uzupełniające szuka z filtrem UPRAWNIEŃ, ale BEZ zawężenia leksykalnego,
którym przyszło pytanie. Uzasadnienie: zawężenie po rzadkim słowie ma wskazać
właściwy DOKUMENT i tę robotę już wykonało; ograniczanie nim jeszcze wyboru
STRONY wewnątrz tego dokumentu wykluczałoby akurat te ustępy, które mówią o rzeczy
innymi słowami — czyli dokładnie te, po które tu sięgamy.
"""

import logging
import re

logger = logging.getLogger(__name__)

MIN_UDZIAL = 0.25        # jaką część trafności musi zebrać dokument-zwycięzca
MAX_DOKLEJONYCH = 3      # ile fragmentów najwyżej dokładamy
LIMIT_KANDYDATOW = 6     # ile pobieramy z dokumentu, zanim odsiejemy już obecne

# Do 1.1.0 stał tu jeszcze warunek MAX_RESZTY = 2: „więcej niż dwa niepokryte słowa
# znaczą, że wyszukiwanie chybiło, a nie że brakuje wątku". Był protezą — liczbą słów
# zgadywaliśmy to, co teraz sprawdzamy wprost, patrz `z_brakujacym_slowem`. Odpadł,
# bo blokował pytania w rodzaju „dolna granica wieku dziecka…", gdzie dwa z trzech
# niepokrytych słów opisują KSZTAŁT odpowiedzi („dolna", „granica"), a nie jej temat.

_SLOWO = re.compile(r"[a-ząćęłńóśźż]{4,}")
_RDZEN = 5               # po tylu znakach porównujemy słowa (odmiana polska)

# Słowa, które nie niosą tematu pytania. Bez tej listy „jakim" czy „mogą" trafiłyby
# do zapytania uzupełniającego i rozmyły je — a akurat te formy w dokumentach
# urzędowych bywają nieobecne, więc wyglądają na „niepokryte".
_STOP = {
    "jaki", "jaka", "jakie", "jakim", "jakiej", "jakiego", "jakich", "ktory", "ktora",
    "ktore", "ktorego", "czym", "kiedy", "gdzie", "dlaczego", "ile", "czy",
    "moge", "moga", "moze", "mozna", "mozliwe", "musze", "musi", "jest", "sie",
    "byc", "bylo", "beda", "bedzie", "mam", "mamy", "chce", "chcialbym",
    "korzystac", "korzysta", "korzystanie", "przystapic", "rozliczyc", "wynosi",
    "znalezc", "otrzymac", "dostac", "zrobic", "zlozyc", "uzyskac",
    "tego", "tym", "tych", "temu", "taki", "takie", "takim",
    "dla", "przy", "oraz", "jako", "przez", "pod", "nad", "bez", "wedlug",
    "prosze", "prosze", "powiedz", "podaj", "wyjasnij",
}

_OGONKI = str.maketrans("ąćęłńóśźż", "acelnoszz")


def bez_ogonkow(tekst: str) -> str:
    """Pisownia bez znaków diakrytycznych — pracownicy piszą i tak, i tak."""
    return (tekst or "").lower().translate(_OGONKI)


def slowa_tresciowe(pytanie: str) -> list[str]:
    """Słowa pytania niosące temat, bez powtórzeń, w kolejności wystąpienia."""
    wynik: list[str] = []
    for m in _SLOWO.finditer((pytanie or "").lower()):
        s = bez_ogonkow(m.group(0))
        if s in _STOP or s in wynik:
            continue
        wynik.append(s)
    return wynik


def niepokryta_reszta(pytanie: str, teksty: list[str]) -> list[str]:
    """Słowa pytania, których NIE MA w podanych fragmentach.

    Porównujemy pięcioznakowe rdzenie, bo polska odmiana rozjeżdża końcówki
    („dzieci" ↔ „dziecka", „wczasów" ↔ „wczasy").
    """
    kontekst = bez_ogonkow(" ".join(teksty))
    return [s for s in slowa_tresciowe(pytanie) if s[:_RDZEN] not in kontekst]


def dokument_zwyciezca(trafienia: list[dict]) -> tuple[int, str, float] | None:
    """(file_id, filename, udział w sumie trafności) dokumentu o największej wadze.

    Sumujemy score zamiast liczyć trafienia: dokument z jednym mocnym fragmentem
    ma być traktowany poważniej niż taki z trzema słabymi.
    """
    waga: dict[int, float] = {}
    nazwa: dict[int, str] = {}
    for t in trafienia:
        fid = t.get("file_id")
        if fid is None:
            continue
        waga[fid] = waga.get(fid, 0.0) + float(t.get("score") or 0.0)
        nazwa[fid] = t.get("filename") or ""
    if not waga:
        return None
    suma = sum(waga.values())
    if suma <= 0:
        return None
    fid = max(waga, key=lambda k: waga[k])
    return fid, nazwa[fid], waga[fid] / suma


def zapytanie_uzupelniajace(reszta: list[str], filename: str) -> str:
    """Niepokryte słowa + tytuł dokumentu (bez rozszerzenia)."""
    tytul = re.sub(r"\.(pdf|docx?|odt|xlsx?|txt)$", "", filename or "", flags=re.I)
    return " ".join(reszta + [tytul]).strip()


def plan_doboru(pytanie: str, w_kontekscie: list[dict]) -> tuple[str, int, list[str]] | None:
    """(zapytanie uzupełniające, file_id, brakujące słowa) albo None, gdy doboru NIE robimy.

    `w_kontekscie` to fragmenty, które FAKTYCZNIE zobaczy model — wołający wybiera
    je tak samo, jak zrobi to węzeł „Chunks Filter" (progiem albo bez progu, gdy
    wyszukiwanie było zawężone). Postać:
    [{"score": float, "file_id": int, "filename": str, "content": str, "page": int}].
    """
    if not w_kontekscie:
        return None                       # pusty kontekst → odmowa jest poprawna

    reszta = niepokryta_reszta(pytanie, [t.get("content") or "" for t in w_kontekscie])
    if not reszta:
        return None                       # kontekst pokrywa pytanie — nie ma czego szukać

    zwyciezca = dokument_zwyciezca(w_kontekscie)
    if not zwyciezca:
        return None
    fid, filename, udzial = zwyciezca
    if udzial < MIN_UDZIAL:
        return None                       # rozstrzelone trafienia — nie ma „tego jednego" dokumentu

    return zapytanie_uzupelniajace(reszta, filename), fid, reszta


async def dobierz_fragmenty(
    pytanie: str,
    w_kontekscie: list[dict],
    filtr_uprawnien: dict | None,
    wektoryzuj,
    szukaj,
) -> list[dict]:
    """Fragmenty do doklejenia do kontekstu: [{"text", "filename", "page"}].

    `w_kontekscie` — fragmenty, które zobaczy model (zob. `plan_doboru`).
    `filtr_uprawnien` — WYŁĄCZNIE warunki RBAC; zawężenia z pytania (rzadkie słowo,
    wskazane pliki) tu nie wchodzą, zob. docstring modułu.
    `wektoryzuj` — asynchroniczne osadzenie tekstu, `szukaj(wektor, filtr, limit)` —
    wyszukiwanie w Qdrancie (wstrzykiwane, żeby dało się testować bez usług).

    Best-effort: każdy błąd kończy się pustą listą, czyli dzisiejszym zachowaniem.
    Filtr uprawnień przenosimy bez zmian i tylko DOKŁADAMY warunek na plik —
    doborem nie da się sięgnąć po dokument, którego użytkownik nie może czytać.
    """
    plan = plan_doboru(pytanie, w_kontekscie)
    if not plan:
        return []
    zapytanie, file_id, reszta = plan

    try:
        w = await wektoryzuj(zapytanie)
    except Exception as e:
        logger.warning(f"[CHAT-DOBOR] Osadzenie zapytania uzupełniającego nieudane: {e}")
        return []

    warunki = list((filtr_uprawnien or {}).get("must") or [])
    warunki.append({"key": "metadata.file_id", "match": {"value": file_id}})
    kandydaci = szukaj(w, {"must": warunki}, LIMIT_KANDYDATOW)

    dobrane = scal_dobrane(z_brakujacym_slowem(kandydaci, reszta), w_kontekscie)
    if dobrane:
        logger.info(
            f"[CHAT-DOBOR] {zapytanie!r} → doklejam {len(dobrane)} fragm. z pliku {file_id}: "
            f"str. {[d.get('page') for d in dobrane]}"
        )
    # `file_id` jedzie razem z fragmentem: nazwa pliku nie identyfikuje dokumentu
    # (w bazie ZCO 9 nazw powtarza się i obejmuje 18 plików), więc bez tego pola
    # cytowanie fragmentu dobranego mogłoby wskazać inny dokument o tej samej nazwie.
    return [
        {"text": d.get("content") or "", "filename": d.get("filename"),
         "page": d.get("page"), "file_id": d.get("file_id")}
        for d in dobrane
        if (d.get("content") or "").strip()
    ]


def z_brakujacym_slowem(kandydaci: list[dict], reszta: list[str]) -> list[dict]:
    """Tylko te fragmenty dokumentu-zwycięzcy, które FAKTYCZNIE zawierają któreś
    z brakujących słów.

    Podobieństwo wektorowe potrafi ustawić właściwy ustęp na końcu listy: przy
    pytaniu o wiek dziecka odpowiedź („w wieku od ukończenia 5-go roku życia…")
    była SZÓSTA z sześciu kandydatów, tuż pod progiem odcięcia — a jednocześnie
    jedynym fragmentem, w którym słowo „wieku" w ogóle występuje. Obecność
    szukanego słowa wskazuje ustęp jednoznacznie tam, gdzie podobieństwo błądzi.

    To sprawdzenie zastąpiło warunek na liczbę niepokrytych słów i przy okazji
    samo broni pytań bez sensu: dla „kary za ewakuację jednorożca" żaden kandydat
    nie zawiera brakującego słowa, więc dobór milczy — bez osobnej reguły.
    """
    rdzenie = [s[:_RDZEN] for s in reszta]
    if not rdzenie:
        return []
    return [
        k for k in kandydaci
        if any(r in bez_ogonkow(k.get("content") or "") for r in rdzenie)
    ]


def scal_dobrane(dobrane: list[dict], obecne: list[dict]) -> list[dict]:
    """Odsiej fragmenty, które i tak są już w kontekście (ta sama strona pliku)."""
    znane = {(t.get("file_id"), t.get("page")) for t in obecne}
    wynik: list[dict] = []
    for d in dobrane:
        klucz = (d.get("file_id"), d.get("page"))
        if klucz in znane:
            continue
        znane.add(klucz)
        wynik.append(d)
        if len(wynik) >= MAX_DOKLEJONYCH:
            break
    return wynik
