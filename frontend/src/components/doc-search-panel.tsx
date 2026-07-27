'use client';

import { useEffect, useState } from 'react';
import { docSchemasApi, docSearchApi, DocTypeSchema, DocSearchHit } from '@/lib/api';

const OPS = [
  { value: 'contains', label: 'zawiera' },
  { value: 'eq', label: 'równe' },
  { value: 'gte', label: '≥ (od)' },
  { value: 'lte', label: '≤ (do)' },
  { value: 'gt', label: '> (po)' },
  { value: 'lt', label: '< (przed)' },
];

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

  useEffect(() => {
    docSchemasApi.list().then(setSchemas).catch(() => { /* rejestr może być pusty */ });
  }, []);

  const currentSchema = schemas.find((s) => s.slug === docType);
  const fieldNames = currentSchema?.fields.map((f) => f.name) || [];

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

  const typeLabel = (slug?: string | null) =>
    schemas.find((s) => s.slug === slug)?.name || slug || '—';

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
              className="px-3 py-1.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
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

        <button
          onClick={search}
          disabled={loading}
          className="w-full px-3 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Szukam…' : 'Szukaj'}
        </button>
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
            <p className="text-xs text-gray-500 mb-2">Znaleziono: {hits.length}</p>
            <ul className="space-y-2">
              {hits.map((h) => (
                <li key={h.id} className="border border-gray-200 rounded-md p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <button
                      onClick={() => download(h.id, h.filename)}
                      className="text-sm text-blue-600 hover:underline text-left break-all"
                    >
                      📄 {h.filename}
                    </button>
                    {h.doc_type && (
                      <span className="shrink-0 px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded-full">
                        {typeLabel(h.doc_type)}
                      </span>
                    )}
                  </div>
                  {h.fields && Object.keys(h.fields).length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {Object.entries(h.fields).map(([k, v]) => (
                        <span key={k} className="text-xs bg-gray-100 text-gray-700 rounded px-1.5 py-0.5">
                          <span className="text-gray-500">{k}:</span> {v}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
