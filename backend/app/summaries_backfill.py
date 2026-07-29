"""Jednorazowe uzupełnienie streszczeń dla dokumentów już przetworzonych.

Nowe pliki dostają streszczenie w trakcie parsowania; ten skrypt obsługuje bazę
sprzed wdrożenia tej funkcji.

    docker exec <backend> python -m app.summaries_backfill            # tylko brakujące
    docker exec <backend> python -m app.summaries_backfill --nadpisz  # wszystkie od nowa

Idzie po jednym dokumencie (jeden strumień vLLM, ok. 15-20 s na dokument), więc
uruchamiaj przy pustej kolejce parsowania.
"""

import asyncio
import sys
import time

from app.database import SessionLocal
from app.models import DocumentStatus, File as FileModel
from app.qdrant_client import ensure_summary_collection, summary_ids
from app.summaries import odswiez_streszczenie


async def main() -> int:
    nadpisz = "--nadpisz" in sys.argv
    if not ensure_summary_collection():
        print("Nie udało się przygotować kolekcji streszczeń — przerywam.")
        return 1

    db = SessionLocal()
    pliki = (
        db.query(FileModel)
        .filter(FileModel.status == DocumentStatus.READY)
        .order_by(FileModel.id)
        .all()
    )
    gotowe = set() if nadpisz else summary_ids()
    do_zrobienia = [f for f in pliki if f.id not in gotowe]
    print(f"dokumentów gotowych: {len(pliki)}, ze streszczeniem: {len(gotowe)}, "
          f"do zrobienia: {len(do_zrobienia)}")

    udane = 0
    start = time.time()
    for i, f in enumerate(do_zrobienia, 1):
        t0 = time.time()
        opis = await odswiez_streszczenie(f.id, f.filename or "", f.folder_id)
        udane += bool(opis)
        print(f"  [{i:3d}/{len(do_zrobienia)}] #{f.id:4d} {time.time() - t0:5.1f}s "
              f"{'ok  ' if opis else 'BRAK'} {(f.filename or '')[:52]}", flush=True)

    db.close()
    print(f"\ngotowe: {udane}/{len(do_zrobienia)} w {(time.time() - start) / 60:.1f} min")
    return 0 if udane == len(do_zrobienia) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
