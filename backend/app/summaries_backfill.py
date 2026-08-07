"""Jednorazowe uzupełnienie streszczeń dla dokumentów już przetworzonych.

Nowe pliki dostają streszczenie w trakcie parsowania; ten skrypt obsługuje bazę
sprzed wdrożenia tej funkcji.

    docker exec <backend> python -m app.summaries_backfill            # tylko brakujące
    docker exec <backend> python -m app.summaries_backfill --braki    # NIEPEŁNE (bez zamienników)
    docker exec <backend> python -m app.summaries_backfill --nadpisz  # wszystkie od nowa

Tryb `--braki` istnieje, bo domyślny pomija każdy plik, który MA już punkt w kolekcji —
a streszczenie bez linii „Inne określenia” punkt ma, tylko jest bezużyteczne dla pytań
zadanych potocznie (zmierzone 2026-08-07: 20 z 188).

Idzie po jednym dokumencie (jeden strumień vLLM, 15-20 s przy wolnym GPU, do ~80 s
gdy równolegle trwa parsowanie), więc uruchamiaj przy pustej kolejce parsowania.
"""

import asyncio
import sys
import time

from app.database import SessionLocal
from app.models import DocumentStatus, File as FileModel
from app.qdrant_client import ensure_summary_collection, summary_ids, summary_payloads
from app.summaries import ma_linie_zamiennikow, odswiez_streszczenie


async def main() -> int:
    nadpisz = "--nadpisz" in sys.argv
    tylko_braki = "--braki" in sys.argv
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
    if nadpisz:
        gotowe = set()
    elif tylko_braki:
        # „Gotowe" = te, które mają PEŁNE streszczenie. Niepełne wracają do kolejki.
        gotowe = {fid for fid, p in summary_payloads().items()
                  if ma_linie_zamiennikow(p.get("opis") or "")}
    else:
        gotowe = summary_ids()
    do_zrobienia = [f for f in pliki if f.id not in gotowe]
    tryb = "wszystkie od nowa" if nadpisz else ("niepełne" if tylko_braki else "brakujące")
    print(f"tryb: {tryb}")
    print(f"dokumentów gotowych: {len(pliki)}, pominiętych: {len(gotowe)}, "
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
