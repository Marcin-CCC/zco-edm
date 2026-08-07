"""Wsadowe generowanie streszczeń sekcyjnych dla dokumentów już przetworzonych.

    docker exec <backend> python -m app.sekcje_backfill              # bez tych, które mają sekcje
    docker exec <backend> python -m app.sekcje_backfill --nadpisz    # wszystko od nowa
    docker exec <backend> python -m app.sekcje_backfill --limit 5    # próbka na rozgrzewkę

Zadanie liczone w godzinach, więc MUSI ustępować czatowi. Nie da się tu użyć
`app.activity.is_chat_active()` — to zwykła zmienna w pamięci procesu backendu,
a backfill startuje jako OSOBNY proces (`docker exec`) i tej zmiennej nie widzi.
Sygnałem widocznym z zewnątrz jest kolejka samego vLLM (`/metrics`): gdy ktoś czeka
na model, wstrzymujemy się przed kolejną sekcją. Nie przerywa to sekcji już rozpoczętej
— chodzi o to, żeby nie DOKŁADAĆ pracy, a nie o wywłaszczanie.
"""

import asyncio
import sys
import time

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentStatus, File as FileModel
from app.qdrant_client import count_sections, ensure_section_collection, section_file_ids
from app.sekcje import odswiez_sekcje, podziel_na_sekcje

PAUZA_S = 10          # ile czekamy w jednym kroku, gdy model jest zajęty
MAX_CZEKANIA_S = 600  # po tym czasie idziemy dalej mimo kolejki (żeby się nie zawiesić)


async def czekaj_na_model() -> float:
    """Poczekaj, aż w kolejce vLLM nikt nie stoi. Zwraca, ile sekund czekano.

    Best-effort: gdy metryk nie da się odczytać, ruszamy dalej — pomiar zajętości
    jest udogodnieniem, a nie warunkiem poprawności.
    """
    czekano = 0.0
    url = f"{settings.VLLM_URL.rstrip('/')}/metrics"
    while czekano < MAX_CZEKANIA_S:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                tekst = (await client.get(url)).text
        except Exception:
            return czekano
        czekajacy = 0.0
        for linia in tekst.splitlines():
            if linia.startswith("vllm:num_requests_waiting"):
                try:
                    czekajacy = float(linia.rsplit(" ", 1)[1])
                except (ValueError, IndexError):
                    czekajacy = 0.0
                break
        if czekajacy < 1:
            return czekano
        await asyncio.sleep(PAUZA_S)
        czekano += PAUZA_S
    return czekano


async def main() -> int:
    nadpisz = "--nadpisz" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if not ensure_section_collection():
        print("Nie udało się przygotować kolekcji sekcji — przerywam.")
        return 1

    db = SessionLocal()
    pliki = (
        db.query(FileModel)
        .filter(FileModel.status == DocumentStatus.READY)
        .order_by(FileModel.id)
        .all()
    )
    gotowe = set() if nadpisz else section_file_ids()

    # Dokumenty mieszczące się w jednym bloku sekcji nie potrzebują — sprawdzamy
    # to przed wywołaniem modelu, żeby nie liczyć ich do postępu.
    do_zrobienia = []
    for f in pliki:
        if f.id in gotowe:
            continue
        ile = len(podziel_na_sekcje(f.id))
        if ile >= 2:
            do_zrobienia.append((f, ile))
    if limit:
        do_zrobienia = do_zrobienia[:limit]

    sekcji_razem = sum(ile for _, ile in do_zrobienia)
    print(f"dokumentów gotowych: {len(pliki)}, z sekcjami już: {len(gotowe)}")
    print(f"do zrobienia: {len(do_zrobienia)} dokumentów = {sekcji_razem} sekcji "
          f"(w kolekcji jest teraz {count_sections()} punktów)")

    udane = czekano_razem = 0
    start = time.time()
    for i, (f, ile) in enumerate(do_zrobienia, 1):
        czekano = await czekaj_na_model()
        czekano_razem += czekano
        t0 = time.time()
        zapisane = await odswiez_sekcje(f.id, f.filename or "", f.folder_id)
        udane += zapisane
        print(f"  [{i:3d}/{len(do_zrobienia)}] #{f.id:4d} {zapisane:2d}/{ile:2d} sekcji "
              f"{time.time() - t0:6.1f}s"
              f"{f' (czekano {czekano:.0f}s)' if czekano else ''} "
              f"{(f.filename or '')[:44]}", flush=True)

    db.close()
    minuty = (time.time() - start) / 60
    print(f"\ngotowe: {udane}/{sekcji_razem} sekcji w {minuty:.1f} min "
          f"(w tym {czekano_razem / 60:.1f} min ustępowania czatowi)")
    return 0 if udane else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
