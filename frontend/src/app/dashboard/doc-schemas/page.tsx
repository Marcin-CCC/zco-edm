'use client';

import { useState, useEffect } from 'react';
import { docSchemasApi, DocTypeSchema } from '@/lib/api';

// Typy pól akceptowane przez backend: string | number | date | enum:v1,v2,...
const FIELD_TYPES = [
  { value: 'string', label: 'Tekst (string)' },
  { value: 'number', label: 'Liczba (number)' },
  { value: 'date', label: 'Data (date)' },
  { value: 'enum', label: 'Lista wartości (enum)' },
];

// Wewnętrzny model pola w formularzu (typ rozbity na bazę + wartości enuma)
interface FieldRow {
  name: string;
  baseType: string;   // string | number | date | enum
  enumValues: string; // gdy enum: "PLN,EUR,..."
  hint: string;
}

const EMPTY_FORM = {
  slug: '',
  name: '',
  criteria: '',
  active: true,
  fields: [] as FieldRow[],
};

function parseType(t: string): { baseType: string; enumValues: string } {
  if (t && t.startsWith('enum:')) return { baseType: 'enum', enumValues: t.slice(5) };
  return { baseType: t || 'string', enumValues: '' };
}

export default function DocSchemasPage() {
  const [schemas, setSchemas] = useState<DocTypeSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [includeInactive, setIncludeInactive] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });

  const fetchSchemas = async () => {
    setLoading(true);
    try {
      const data = await docSchemasApi.list(includeInactive);
      setSchemas(data);
    } catch (err: any) {
      setError(err.message || 'Błąd pobierania schematów');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchemas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeInactive]);

  const resetForm = () => {
    setForm({ ...EMPTY_FORM, fields: [] });
    setShowForm(false);
    setEditingSlug(null);
  };

  const handleNew = () => {
    setForm({ ...EMPTY_FORM, fields: [] });
    setEditingSlug(null);
    setShowForm(true);
  };

  const handleEdit = (s: DocTypeSchema) => {
    setForm({
      slug: s.slug,
      name: s.name || '',
      criteria: s.criteria || '',
      active: s.active,
      fields: (s.fields || []).map((f) => {
        const { baseType, enumValues } = parseType(f.type);
        return { name: f.name || '', baseType, enumValues, hint: f.hint || '' };
      }),
    });
    setEditingSlug(s.slug);
    setShowForm(true);
  };

  // ---- operacje na wierszach pól ----
  const addField = () =>
    setForm((f) => ({ ...f, fields: [...f.fields, { name: '', baseType: 'string', enumValues: '', hint: '' }] }));

  const updateField = (i: number, patch: Partial<FieldRow>) =>
    setForm((f) => ({ ...f, fields: f.fields.map((row, idx) => (idx === i ? { ...row, ...patch } : row)) }));

  const removeField = (i: number) =>
    setForm((f) => ({ ...f, fields: f.fields.filter((_, idx) => idx !== i) }));

  // Kolejność pól to NIE jest kosmetyka: w tej samej kolejności wychodzą kolumny
  // w eksporcie listy do XLSX (zob. backend/app/eksport.py). Dzięki temu układ
  // arkusza ustawia się tam, gdzie i tak definiuje się pola — bez osobnego
  // kreatora eksportu i bez drugiego miejsca, które trzeba pamiętać.
  //
  // Strzałki zamiast przeciągania: pól jest 4–8, więc zysk z przeciągania jest
  // znikomy, a kosztowałoby obsługę dotyku i dostępności.
  const moveField = (i: number, kierunek: -1 | 1) =>
    setForm((f) => {
      const cel = i + kierunek;
      if (cel < 0 || cel >= f.fields.length) return f;
      const fields = [...f.fields];
      [fields[i], fields[cel]] = [fields[cel], fields[i]];
      return { ...f, fields };
    });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const payload: DocTypeSchema = {
      slug: form.slug.trim().toLowerCase(),
      name: form.name.trim(),
      criteria: form.criteria.trim() || null,
      active: form.active,
      fields: form.fields
        .filter((f) => f.name.trim())
        .map((f) => ({
          name: f.name.trim(),
          type: f.baseType === 'enum' ? `enum:${f.enumValues.trim()}` : f.baseType,
          hint: f.hint.trim() || null,
        })),
    };
    try {
      await docSchemasApi.upsert(payload);
      resetForm();
      fetchSchemas();
    } catch (err: any) {
      setError(err.message || 'Błąd zapisu schematu');
    }
  };

  const handleDelete = async (slug: string) => {
    if (!confirm(`Czy na pewno usunąć schemat „${slug}"?`)) return;
    setError('');
    try {
      await docSchemasApi.delete(slug);
      fetchSchemas();
    } catch (err: any) {
      setError(err.message || 'Błąd usuwania');
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-gray-800">Schematy dokumentów</h1>
        <button
          onClick={handleNew}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          + Dodaj schemat
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-6">
        Typy dokumentów i pola nagłówkowe, po których będzie można je klasyfikować i filtrować.
        Propozycje pochodzą z indukcji na próbkach — tutaj je korygujesz i zatwierdzasz.
      </p>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {/* Formularz */}
      {showForm && (
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            {editingSlug ? `Edytuj schemat: ${editingSlug}` : 'Nowy schemat'}
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Slug (identyfikator){editingSlug && <span className="text-gray-400 font-normal"> — niezmienialny</span>}
                </label>
                <input
                  type="text"
                  value={form.slug}
                  onChange={(e) => setForm({ ...form, slug: e.target.value })}
                  disabled={!!editingSlug}
                  placeholder="np. zarzadzenie"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
                  required
                />
                <p className="text-xs text-gray-400 mt-1">małe litery, cyfry, „-" lub „_" (2–50 znaków)</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nazwa</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="np. Zarządzenie"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Kryteria klasyfikacji <span className="text-gray-400 font-normal">(opcjonalnie)</span>
              </label>
              <textarea
                value={form.criteria}
                onChange={(e) => setForm({ ...form, criteria: e.target.value })}
                rows={2}
                placeholder="Jak rozpoznać ten typ dokumentu (wskazówki dla klasyfikatora)."
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Pola */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700">
                  Pola nagłówkowe
                  <span className="ml-2 font-normal text-xs text-gray-500">
                    kolejność wyznacza układ kolumn przy pobieraniu listy do Excela
                  </span>
                </label>
                <button
                  type="button"
                  onClick={addField}
                  className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                >
                  + pole
                </button>
              </div>

              {form.fields.length === 0 ? (
                <p className="text-sm text-gray-400 py-2">Brak pól — dodaj pierwsze przyciskiem „+ pole".</p>
              ) : (
                <div className="space-y-2">
                  {form.fields.map((row, i) => (
                    <div key={i} className="flex flex-wrap items-start gap-2">
                      <div className="flex flex-col leading-none pt-1">
                        <button
                          type="button"
                          onClick={() => moveField(i, -1)}
                          disabled={i === 0}
                          title="W górę (wcześniejsza kolumna w Excelu)"
                          className="px-1 text-gray-500 hover:text-gray-800 disabled:text-gray-200"
                        >
                          ▲
                        </button>
                        <button
                          type="button"
                          onClick={() => moveField(i, 1)}
                          disabled={i === form.fields.length - 1}
                          title="W dół (późniejsza kolumna w Excelu)"
                          className="px-1 text-gray-500 hover:text-gray-800 disabled:text-gray-200"
                        >
                          ▼
                        </button>
                      </div>
                      <input
                        type="text"
                        value={row.name}
                        onChange={(e) => updateField(i, { name: e.target.value })}
                        placeholder="nazwa pola (np. data)"
                        className="flex-1 min-w-[140px] px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                      <select
                        value={row.baseType}
                        onChange={(e) => updateField(i, { baseType: e.target.value })}
                        className="px-3 py-2 border border-gray-300 rounded-md text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      >
                        {FIELD_TYPES.map((t) => (
                          <option key={t.value} value={t.value}>{t.label}</option>
                        ))}
                      </select>
                      {row.baseType === 'enum' && (
                        <input
                          type="text"
                          value={row.enumValues}
                          onChange={(e) => updateField(i, { enumValues: e.target.value })}
                          placeholder="wartości: PLN,EUR,USD"
                          className="flex-1 min-w-[140px] px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                      )}
                      <input
                        type="text"
                        value={row.hint}
                        onChange={(e) => updateField(i, { hint: e.target.value })}
                        placeholder="podpowiedź (opcjonalnie)"
                        className="flex-1 min-w-[140px] px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                      <button
                        type="button"
                        onClick={() => removeField(i)}
                        className="px-3 py-2 text-red-600 hover:text-red-800 text-sm font-medium"
                        title="Usuń pole"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(e) => setForm({ ...form, active: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Aktywny</span>
              </label>
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={resetForm}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
              >
                Anuluj
              </button>
              <button
                type="submit"
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
              >
                {editingSlug ? 'Zapisz zmiany' : 'Dodaj schemat'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filtr */}
      <div className="flex items-center justify-end mb-2">
        <label className="flex items-center text-sm text-gray-600">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          Pokaż nieaktywne
        </label>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="text-center py-8 text-gray-500">Ładowanie...</div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Pola</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Akcje</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {schemas.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                    Brak schematów — dodaj pierwszy przyciskiem „+ Dodaj schemat".
                  </td>
                </tr>
              ) : (
                schemas.map((s) => (
                  <tr key={s.slug} className="hover:bg-gray-50 align-top">
                    <td className="px-4 py-3 text-sm text-gray-800">
                      <div className="font-medium">{s.name}</div>
                      <div className="text-gray-400 text-xs">{s.slug}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {(s.fields || []).length === 0 ? (
                        <span className="text-gray-400">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {s.fields.map((f) => (
                            <span
                              key={f.name}
                              className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded"
                              title={f.type}
                            >
                              {f.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                        s.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                      }`}>
                        {s.active ? 'Aktywny' : 'Nieaktywny'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleEdit(s)}
                          className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                        >
                          Edytuj
                        </button>
                        <button
                          onClick={() => handleDelete(s.slug)}
                          className="text-red-600 hover:text-red-800 text-xs font-medium"
                        >
                          Usuń
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
