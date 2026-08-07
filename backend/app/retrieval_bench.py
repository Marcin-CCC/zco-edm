"""Pomiar wyszukiwania na stałym zestawie pytań — przed i po zmianie.

    docker exec <backend> python -m app.retrieval_bench
    docker exec <backend> python -m app.retrieval_bench --zapisz /tmp/przed.json
    docker exec <backend> python -m app.retrieval_bench --porownaj /tmp/przed.json

Po co: dotąd każdą zmianę w wyszukiwaniu oceniałem doraźnie, pytanie po pytaniu.
To wystarcza, dopóki zmiana dotyczy jednego przypadku, ale przestaje wystarczać
przy zmianach, które przestawiają RANKING dla wszystkich pytań naraz — a taką
zmianą będą streszczenia sekcyjne (188 → ~485 celów wyszukiwania w warstwie,
o której wiemy, że nie rozdziela trafień od nietrafień wartością score).

Pomiar idzie przez `app.chat.zakres.zaplanuj_zakres`, czyli DOKŁADNIE tę funkcję,
której używa czat. To nie jest szczegół: wcześniejszy błąd wziął się stąd, że
pomiar odtwarzał ścieżkę retrievalu ręcznie i odtworzył inną, niż szła naprawdę.

Czego ten pomiar NIE robi: nie wywołuje modelu i nie ocenia treści odpowiedzi.
Mierzy wyłącznie to, co da się zmierzyć powtarzalnie — czy właściwy dokument
w ogóle trafia do kontekstu. Odpowiedź modelu przy tym samym kontekście bywa
różna (temperatura), więc nie nadaje się na miarę regresji.
"""

import asyncio
import json
import sys
from pathlib import Path

from app.chat.streszczenia import PROG_FRAGMENTU
from app.chat.zakres import zaplanuj_zakres

ZESTAW = Path(__file__).with_name("retrieval_bench_pytania.json")


def _sciezka(plan) -> str:
    """Którą z czterech dróg poszło pytanie (zob. app/chat/zakres.py)."""
    if plan.wskazane_pliki:
        return "pliki"
    if plan.terminy:
        return "terminy"
    if plan.wskazane_streszczeniem:
        return "streszcz." if plan.bez_progu else "uzupeł."
    return "zwykła"


def _ocena(wpis: dict, plan) -> tuple[bool, str, float]:
    """(czy poprawne, dokument dominujący, udział oczekiwanego w kontekście).

    Kryterium to DOMINACJA, nie obecność. Pierwsza wersja pytała tylko, czy
    oczekiwany dokument trafił do kontekstu — i zaliczyła jako poprawne pytanie
    „od jakiego wieku dziecka przysługuje grusza?", na które padła odpowiedź
    z polisy ubezpieczeniowej. Regulamin ZFŚS BYŁ w kontekście, tyle że w mniejszości
    wobec polis, więc model oparł się na nich. Obecność jest warunkiem koniecznym,
    nie wystarczającym; liczy się, co w kontekście przeważa.
    """
    from app.chat.dobor import dokument_zwyciezca

    w_kontekscie = list(plan.w_kontekscie)
    oczekiwany = wpis.get("oczekiwany")

    if not w_kontekscie:
        return (oczekiwany is None), "pusty kontekst", 0.0

    zwyciezca = dokument_zwyciezca(w_kontekscie)
    nazwa_zwyciezcy = (zwyciezca[1] if zwyciezca else "?") or "?"

    if oczekiwany is None:
        return False, f"kontekst z {len(w_kontekscie)} fragm.", 0.0
    if oczekiwany == "":
        return True, nazwa_zwyciezcy[:34], 0.0                  # tylko obserwacja

    # Lista wariantów: ten sam dokument bywa w bazie pod różnymi nazwami, a bywa też,
    # że na pytanie poprawnie odpowiada kilka dokumentów z jednej rodziny.
    warianty = [oczekiwany] if isinstance(oczekiwany, str) else list(oczekiwany)
    pasuje = lambda n: any(w.lower() in n.lower() for w in warianty)   # noqa: E731

    nazwy = [str(t.get("filename") or "") for t in w_kontekscie]
    nazwy += [str(d.get("filename") or "") for d in plan.dobrane]
    udzial = sum(1 for n in nazwy if pasuje(n)) / len(nazwy)
    return pasuje(nazwa_zwyciezcy), nazwa_zwyciezcy[:34], udzial


async def zmierz(znane_rdzenie: set[str]) -> list[dict]:
    dane = json.loads(ZESTAW.read_text(encoding="utf-8"))
    wyniki = []
    for wpis in dane["pytania"]:
        pytanie = wpis["pytanie"]
        plan = await zaplanuj_zakres(
            pytanie=pytanie,
            search_query=pytanie,          # bez historii — pomiar ma być powtarzalny
            file_ids=None,
            folder_filter_enabled=False,   # jak administrator: bez ograniczeń RBAC
            allowed_folder_ids=[],
            znane_rdzenie=znane_rdzenie,
        )
        nad_progiem = sum(1 for t in plan.trafienia if t["score"] >= PROG_FRAGMENTU)
        ok, opis, udzial = _ocena(wpis, plan)
        wyniki.append({
            "pytanie": pytanie,
            "oczekiwany": wpis.get("oczekiwany"),
            "obserwacja": wpis.get("oczekiwany") == "",
            "ok": ok,
            "sciezka": _sciezka(plan),
            "nad_progiem": nad_progiem,
            "w_kontekscie": len(plan.w_kontekscie),
            "dobrane": len(plan.dobrane),
            "udzial": round(udzial, 2),
            "szczyt": round(plan.trafienia[0]["score"], 3) if plan.trafienia else 0.0,
            "pierwszy": opis,
        })
    return wyniki


def wypisz(wyniki: list[dict]) -> None:
    print(f"{'':2} {'pytanie':50} {'ścieżka':9} {'>próg':>5} {'kontekst':>8} "
          f"{'dobr':>4} {'udział':>6}  dokument dominujący")
    for w in wyniki:
        znak = "  " if w["obserwacja"] else ("ok" if w["ok"] else "!!")
        print(f"{znak} {w['pytanie'][:50]:50} {w['sciezka']:9} {w['nad_progiem']:5} "
              f"{w['w_kontekscie']:8} {w['dobrane']:4} {w.get('udzial', 0):6.0%}  {w['pierwszy']}")
    oceniane = [w for w in wyniki if not w["obserwacja"]]
    udane = sum(1 for w in oceniane if w["ok"])
    print(f"\nWYNIK: {udane}/{len(oceniane)} poprawnych "
          f"({len(wyniki) - len(oceniane)} pytań tylko obserwowanych)")


def porownaj(stare: list[dict], nowe: list[dict]) -> None:
    po_pytaniu = {w["pytanie"]: w for w in stare}
    zmiany = 0
    print("\n--- RÓŻNICE WOBEC ZAPISU ---")
    for w in nowe:
        s = po_pytaniu.get(w["pytanie"])
        if not s:
            print(f"  NOWE  {w['pytanie'][:60]}")
            zmiany += 1
            continue
        if s["ok"] != w["ok"]:
            kierunek = "POPRAWA " if w["ok"] else "REGRESJA"
            print(f"  {kierunek} {w['pytanie'][:56]}  ({s['pierwszy']} → {w['pierwszy']})")
            zmiany += 1
        elif s["sciezka"] != w["sciezka"] or s["w_kontekscie"] != w["w_kontekscie"]:
            print(f"  zmiana   {w['pytanie'][:56]}  "
                  f"{s['sciezka']}/{s['w_kontekscie']} → {w['sciezka']}/{w['w_kontekscie']}")
            zmiany += 1
    if not zmiany:
        print("  brak zmian")


async def main() -> int:
    from app.chat.lexical import rdzenie_z_rejestru
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        znane = rdzenie_z_rejestru(db)
    finally:
        db.close()

    wyniki = await zmierz(znane)
    wypisz(wyniki)

    if "--zapisz" in sys.argv:
        sciezka = Path(sys.argv[sys.argv.index("--zapisz") + 1])
        sciezka.write_text(json.dumps(wyniki, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nzapisano: {sciezka}")
    if "--porownaj" in sys.argv:
        sciezka = Path(sys.argv[sys.argv.index("--porownaj") + 1])
        porownaj(json.loads(sciezka.read_text(encoding="utf-8")), wyniki)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
