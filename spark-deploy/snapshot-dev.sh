#!/usr/bin/env bash
# Kopia bazy produkcyjnej ze Sparka do LOKALNEJ bazy deweloperskiej.
#
#   bash spark-deploy/snapshot-dev.sh                # pełna kopia (z treścią dokumentów)
#   bash spark-deploy/snapshot-dev.sh --no-content   # bez treści OCR, czatów i ocen
#
# Kierunek jest jednostronny i taki ma pozostać: KOD IDZIE W GÓRĘ (git → CI → Spark),
# DANE SCHODZĄ W DÓŁ. Ten skrypt niczego na Sparku nie zapisuje — wykonuje wyłącznie
# `pg_dump`, czyli odczyt.
#
# UWAGA — to są dane klienta. Pełny zrzut zawiera treść dokumentów medycznych
# (wynik OCR), historię czatów i oceny odpowiedzi. Przeniesienie ich na laptop to
# decyzja, a nie czynność techniczna. Do większości pracy wystarcza `--no-content`:
# zostają użytkownicy, foldery, uprawnienia i metadane plików. Pełnej kopii używaj
# tylko wtedy, gdy zadanie jej wymaga (np. strojenie wyszukiwania) i kasuj ją po
# zakończeniu pracy.
set -euo pipefail

SPARK_HOST="${SPARK_HOST:-spark}"          # alias z ~/.ssh/config
SPARK_DB_CONTAINER="edm-zco-postgres"
LOCAL_DB_CONTAINER="${LOCAL_DB_CONTAINER:-edm-dev-pg}"
DB_NAME="edmdatabase"
DB_USER="postgres"

export MSYS_NO_PATHCONV=1                  # Git Bash na Windows psuje ścieżki w docker exec

BEZ_TRESCI=0
[[ "${1:-}" == "--no-content" ]] && BEZ_TRESCI=1

if ! docker ps --format '{{.Names}}' | grep -qx "$LOCAL_DB_CONTAINER"; then
  echo "BŁĄD: nie działa lokalny kontener bazy '$LOCAL_DB_CONTAINER'." >&2
  echo "Uruchom go:" >&2
  echo "  docker run -d --name $LOCAL_DB_CONTAINER --restart unless-stopped \\" >&2
  echo "    -e POSTGRES_PASSWORD=tajne_haslo -e POSTGRES_DB=$DB_NAME \\" >&2
  echo "    -p 15432:5432 postgres:15-alpine" >&2
  exit 1
fi

echo "1/4  Odtwarzam pustą bazę lokalną..."
docker exec -i "$LOCAL_DB_CONTAINER" psql -q -U "$DB_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE)" \
  -c "CREATE DATABASE $DB_NAME" > /dev/null

echo "2/4  Pobieram zrzut ze Sparka (tylko odczyt)..."
ssh -o BatchMode=yes "$SPARK_HOST" \
  "docker exec $SPARK_DB_CONTAINER pg_dump -U $DB_USER -d $DB_NAME" \
  | docker exec -i "$LOCAL_DB_CONTAINER" psql -q -U "$DB_USER" -d "$DB_NAME" > /dev/null

if [[ $BEZ_TRESCI -eq 1 ]]; then
  echo "3/4  Usuwam treści (tryb --no-content)..."
  docker exec -i "$LOCAL_DB_CONTAINER" psql -q -U "$DB_USER" -d "$DB_NAME" <<'SQL' > /dev/null
DO $$
BEGIN
  IF to_regclass('public.files')            IS NOT NULL THEN UPDATE files SET ocr_result = NULL; END IF;
  IF to_regclass('public.documents')        IS NOT NULL THEN UPDATE documents SET raw_text = NULL; END IF;
  IF to_regclass('public.document_pages')   IS NOT NULL THEN UPDATE document_pages SET raw_content = NULL; END IF;
  IF to_regclass('public.embeddings')       IS NOT NULL THEN UPDATE embeddings SET content = NULL; END IF;
  IF to_regclass('public.messages')         IS NOT NULL THEN UPDATE messages SET content = '[treść usunięta ze zrzutu]'; END IF;
  IF to_regclass('public.oceny_odpowiedzi') IS NOT NULL THEN
    UPDATE oceny_odpowiedzi SET pytanie = NULL, odpowiedz = NULL, diagnostyka = NULL;
  END IF;
END $$;
SQL
else
  echo "3/4  Tryb pełny — treść dokumentów ZOSTAJE w kopii lokalnej."
fi

echo "4/4  Gotowe. Stan lokalnej bazy:"
docker exec -i "$LOCAL_DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT (SELECT count(*) FROM users) AS uzytkownicy,
          (SELECT count(*) FROM folders) AS foldery,
          (SELECT count(*) FROM files) AS pliki,
          (SELECT count(*) FROM files WHERE ocr_result IS NOT NULL) AS pliki_z_trescia"

echo
echo "Backend deweloperski łączy się do niej przez host.docker.internal:15432 (backend/.env.dev)."
[[ $BEZ_TRESCI -eq 0 ]] && echo "Pamiętaj: ta kopia zawiera dokumenty klienta. Skasuj ją, gdy przestanie być potrzebna."
