'use client';

import { useEffect, useState } from 'react';
import { IconDownload } from '@/components/icons';
import { PozycjaDokumentu, zHitow } from '@/components/pozycja-dokumentu';
import { Button } from '@/components/ui/primitives';
import { docSchemasApi, docSearchApi, DocTypeSchema, DocSearchHit } from '@/lib/api';
import { pobierzListeXlsx } from '@/lib/eksport-xlsx';

const OPS = [
  { value: 'contains', label: 'zawiera' },
  { value: 'eq', label: 'równe' },
  { value: 'gte', label: '≥ (od)' },
  { value: 'lte', label: '≤ (do)' },
  { value: 'gt', label: '> (po)' },
  { value: 'lt', label: '< (przed)' },
];

/** 1 dokument, 2 dokumenty, 5 dokumentów. */
function odmianaDokumentow(n: number): string {
  if (n === 1) return 'dokument';
  const ost = n % 10;
  const dwie = n % 100;
  return ost >= 2 && ost <= 4 && (dwie < 10 || dwie >= 20) ? 'dokumenty' : 'dokumentów';
}

interface FilterRow {
  field: string;
  op: string;
  value: string;
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function DocSearchPanel({ onClose }: { onClose?: () => void }) {
  const [schemas, setSchemas] = useState<DocTypeSchema[]>([]);
  const [docType, setDocType] = useState('');
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [hits, setHits] = useState<DocSearchHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [nlQuery, setNlQuery] = useState('');
  const [nlLoading, setNlLoading] = useState(false);
  const [eksportTrwa, setEksportTrwa] = useState(false);

  /** Pobierz wyniki jako arkusz. Nazwę pliku buduje backend z pytania po polsku —
   *  tak samo jak w czacie robi to z pytania użytkownika. */
  const pobierzXlsx = async () => {
    if (!hits?.length) return;
    setEksportTrwa(true);
    try {
      await pobierzListeXlsx(hits.map((h) => h.id), nlQuery);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Nie udało się pobrać arkusza.');
    } finally {
      setEksportTrwa(false);
    }
  };

  useEffect(() => {
    docSchemasApi.list().then(setSchemas).catch(() => { /* rejestr może być pusty */ });
  }, []);

  const currentSchema = schemas.find((s) => s.slug === docType);
  const fieldNames = currentSchema?.fields.map((f) => f.name) || [];

  // „Szukaj" ma sens dopiero, gdy jest jakiekolwiek kryterium (typ albo warunek)
  const hasCriteria = !!docType || filters.some((f) => f.field.trim() && f.value.trim());

  const addFilter = () => setFilters((f) => [...f, { field: '', op: 'contains', value: '' }]);
  const updateFilter = (i: number, patch: Partial<FilterRow>) =>
    setFilters((f) => f.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeFilter = (i: number) => setFilters((f) => f.filter((_, idx) => idx !== i));

  const search = async () => {
    setLoading(true);
    setError('');
    try {
      const body = {
        doc_type: docType || null,
        filters: filters.filter((f) => f.field.trim() && f.value.trim()),
      };
      setHits(await docSearchApi.search(body));
    } catch (e: any) {
      setError(e.message || 'Błąd wyszukiwania');
    } finally {
      setLoading(false);
    }
  };

  // Pytanie po polsku → LLM rozpoznaje filtr → wypełnia formularz + pokazuje wyniki
  const nlSearch = async () => {
    if (!nlQuery.trim()) return;
    setNlLoading(true);
    setError('');
    try {
      const res = await docSearchApi.nl(nlQuery.trim());
      setDocType(res.filter.doc_type || '');
      setFilters((res.filter.filters || []).map((f) => ({ field: f.field, op: f.op, value: f.value })));
      setHits(res.hits);
      if (res.unknown_type) {
        setError(
          `W systemie nie ma rodzaju dokumentów „${res.unknown_type}". ` +
          `Rozpoznawane rodzaje: ${(res.known_types || []).join(', ')}.`
        );
      }
    } catch (e: any) {
      setError(e.message || 'Nie udało się zrozumieć zapytania');
    } finally {
      setNlLoading(false);
    }
  };

  const download = async (id: number, filename: string) => {
    try {
      const res = await fetch(`/api/files/${id}/download`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`Błąd pobierania (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (e: any) {
      alert(e?.message || `Nie udało się otworzyć „${filename}".`);
    }
  };

  // slug → nazwa czytelna; wspólna konwersja wyników oczekuje słownika
  const nazwyTypow = Object.fromEntries(schemas.map((sch) => [sch.slug, sch.name]));

  return (
    <div className="hidden lg:flex flex-1 min-w-[320px] flex-col bg-white rounded-lg shadow border border-gray-200">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Wyszukiwarka po polach</h2>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-lg leading-none px-1"
            title="Zwiń wyszukiwarkę"
          >
            ✕
          </button>
        )}
      </div>

      {/* Formularz */}
      <div className="p-4 border-b border-gray-200 space-y-3">
        {schemas.length === 0 && (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
            Brak zdefiniowanych typów. Dodaj je w Administracja → Schematy dokumentów.
          </p>
        )}

        {/* Pytanie po polsku → filtr (NL→filtr) */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Zapytaj po polsku</label>
          <div className="flex gap-1.5">
            <input
              type="text"
              value={nlQuery}
              onChange={(e) => setNlQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') nlSearch(); }}
              placeholder="np. wszystkie zarządzenia z 2023"
              className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-md text-sm"
            />
            <button
              onClick={nlSearch}
              disabled={nlLoading || !nlQuery.trim()}
              className="px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {nlLoading ? '…' : 'Zapytaj'}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-1">Rozpoznane zapytanie wypełni filtr poniżej — możesz go poprawić i wyszukać ponownie.</p>
        </div>

        <div className="border-t border-gray-100 pt-3">
          <label className="block text-xs font-medium text-gray-600 mb-1">Typ dokumentu</label>
          <select
            value={docType}
            onChange={(e) => { setDocType(e.target.value); setFilters([]); }}
            className="w-full px-2 py-1.5 border border-gray-300 rounded-md text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="">— dowolny typ —</option>
            {schemas.map((s) => (
              <option key={s.slug} value={s.slug}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          {filters.map((row, i) => (
            <div key={i} className="flex items-center gap-1.5">
              {fieldNames.length > 0 ? (
                <select
                  value={row.field}
                  onChange={(e) => updateFilter(i, { field: e.target.value })}
                  className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-md text-sm bg-white"
                >
                  <option value="">— pole —</option>
                  {fieldNames.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              ) : (
                <input
                  type="text"
                  value={row.field}
                  onChange={(e) => updateFilter(i, { field: e.target.value })}
                  placeholder="pole"
                  className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-md text-sm"
                />
              )}
              <select
                value={row.op}
                onChange={(e) => updateFilter(i, { op: e.target.value })}
                className="px-1.5 py-1.5 border border-gray-300 rounded-md text-sm bg-white shrink-0"
              >
                {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <input
                type="text"
                value={row.value}
                onChange={(e) => updateFilter(i, { value: e.target.value })}
                placeholder="wartość"
                className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-md text-sm"
              />
              <button
                onClick={() => removeFilter(i)}
                className="px-1.5 text-red-500 hover:text-red-700 text-sm shrink-0"
                title="Usuń warunek"
              >
                ✕
              </button>
            </div>
          ))}
          <button onClick={addFilter} className="text-blue-600 hover:text-blue-800 text-xs font-medium">
            + warunek
          </button>
        </div>

        <div>
          <button
            onClick={search}
            disabled={loading || !hasCriteria}
            className="px-6 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            {loading ? 'Szukam…' : 'Szukaj'}
          </button>
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>

      {/* Wyniki */}
      <div className="flex-1 overflow-y-auto p-4">
        {hits === null ? (
          <p className="text-xs text-gray-400 text-center mt-6">
            Ustaw kryteria i kliknij „Szukaj".
          </p>
        ) : hits.length === 0 ? (
          <p className="text-xs text-gray-400 text-center mt-6">Brak dokumentów spełniających kryteria.</p>
        ) : (
          <>
            <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[12px] text-app-muted">
                Znaleziono {hits.length} {odmianaDokumentow(hits.length)}.
              </p>
              {/* Eksport tej samej listy, którą widać niżej — kolumny i kolejność ustala
                  rejestr schematów, nazwa pliku powstaje z pytania po polsku. */}
              <Button small onClick={pobierzXlsx} disabled={eksportTrwa}>
                <IconDownload size={15} />
                {eksportTrwa ? 'Przygotowuję arkusz…' : 'Pobierz tę listę w pliku XLSX'}
              </Button>
            </div>
            {/* Ten sam format co lista dokumentów pod odpowiedzią czatu — bo to ten
                sam rodzaj wyniku z tej samej ścieżki (`/api/doc-search`). Pola
                opisowe zniknęły z kafelka: numer albo data i tak trafia do etykiety,
                a reszta rozsadzała listę tym bardziej, im bogatszy schemat. Pełny
                zestaw pól daje eksport do arkusza. */}
            <div className="grid gap-2">
              {zHitow(hits, nazwyTypow).map((d, i) => (
                <PozycjaDokumentu
                  key={d.file_id ?? i}
                  d={d}
                  numer={i + 1}
                  otworz={d.file_id ? () => download(d.file_id!, d.filename || '') : undefined}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
