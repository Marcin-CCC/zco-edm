'use client';

import { useState, useEffect } from 'react';

import { IconClose, IconEdit, IconPlus, IconTrash } from '@/components/icons';
import { SortableFields } from '@/components/sortable-fields';
import {
  Badge, Button, Card, EmptyState, Field, IconButton, PageHeader, RowActions,
  Sub, Table, Td, Th, inputClass,
} from '@/components/ui/primitives';
import { docSchemasApi, DocTypeSchema } from '@/lib/api';

// Typy pól akceptowane przez backend: string | number | money | date | enum:v1,v2,...
// „Kwota" różni się od „Liczby" tym, co dzieje się dalej: w eksporcie do Excela
// trafia jako liczba z groszami i separatorem tysięcy, więc kolumna się sumuje.
const FIELD_TYPES = [
  { value: 'string', label: 'Tekst (string)' },
  { value: 'date', label: 'Data (date)' },
  { value: 'number', label: 'Liczba (number)' },
  { value: 'money', label: 'Kwota (money)' },
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
  name_pattern: '',
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
      name_pattern: s.name_pattern || '',
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
  // Kolejność zmienia się przeciąganiem za uchwyt (makieta 1.5). Obsługę
  // klawiatury zapewniają strzałki na uchwycie — zob. SortableFields.
  const setFields = (fields: FieldRow[]) => setForm((f) => ({ ...f, fields }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const payload: DocTypeSchema = {
      slug: form.slug.trim().toLowerCase(),
      name: form.name.trim(),
      criteria: form.criteria.trim() || null,
      name_pattern: form.name_pattern.trim() || null,
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
      <PageHeader
        title="Schematy dokumentów"
        description="Typy dokumentów i pola nagłówkowe, po których klasyfikujemy i filtrujemy pliki. Propozycje pochodzą z indukcji na próbkach — tutaj je korygujesz i zatwierdzasz."
        actions={
          !showForm && (
            <Button variant="primary" onClick={handleNew}>
              <IconPlus size={18} />
              Dodaj schemat
            </Button>
          )
        }
      />

      {error && (
        <div className="mb-4 rounded-ctl border border-[#fecdd3] bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {error}
        </div>
      )}

      {/* Formularz */}
      {showForm && (
        <Card className="mb-5 p-[18px]">
          <h2 className="mb-4 text-base font-bold text-app-text">
            {editingSlug ? `Edytuj schemat: ${editingSlug}` : 'Nowy schemat'}
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Field
                  label={`Slug (identyfikator)${editingSlug ? ' — niezmienialny' : ''}`}
                  hint={'małe litery, cyfry, "-" lub "_" (2–50 znaków)'}
                >
                  <input
                    type="text"
                    value={form.slug}
                    onChange={(e) => setForm({ ...form, slug: e.target.value })}
                    disabled={!!editingSlug}
                    placeholder="np. zarzadzenie"
                    className={`${inputClass} disabled:bg-app-bg disabled:text-app-muted`}
                    required
                  />
                </Field>
              </div>
              <div>
                <Field label="Nazwa">
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="np. Zarządzenie"
                    className={inputClass}
                    required
                  />
                </Field>
              </div>
            </div>

            <div>
              <Field label="Kryteria klasyfikacji (opcjonalnie)">
                <textarea
                  value={form.criteria}
                  onChange={(e) => setForm({ ...form, criteria: e.target.value })}
                  rows={2}
                  placeholder="Jak rozpoznać ten typ dokumentu (wskazówki dla klasyfikatora)."
                  className={`${inputClass} h-auto py-2`}
                />
              </Field>
            </div>

            <div>
              <Field label="Wzorzec nazwy pliku (opcjonalnie)">
                <input
                  value={form.name_pattern}
                  onChange={(e) => setForm({ ...form, name_pattern: e.target.value })}
                  placeholder="{typ}-nr-{numer}-{data}"
                  className={`${inputClass} font-mono`}
                />
              </Field>
              <p className="mt-1 text-xs text-app-muted">
                W nawiasach klamrowych nazwy pól nagłówkowych tego typu oraz <code>{'{typ}'}</code>.
                Polskie znaki, spacje i znaki zakazane w nazwach plików zamieniamy na myślnik,
                rozszerzenie dokładamy z oryginału. Puste = dla tej kategorii nie proponujemy nazw.
              </p>
            </div>

            {/* Pola */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="block text-[13px] font-medium text-app-text">
                  Pola nagłówkowe
                  <span className="ml-2 text-xs font-normal text-app-muted">
                    kolejność (przeciąganie za uchwyt) wyznacza układ kolumn w arkuszu
                  </span>
                </span>
                <Button type="button" variant="ghost" small onClick={addField}>
                  <IconPlus size={16} />
                  pole
                </Button>
              </div>

              {form.fields.length === 0 ? (
                <p className="py-2 text-sm text-app-muted">Brak pól — dodaj pierwsze przyciskiem „+ pole".</p>
              ) : (
                <SortableFields
                  items={form.fields}
                  onReorder={setFields}
                  klucz={(_, i) => String(i)}
                  renderItem={(row, i) => (
                    <>
                      <input
                        type="text"
                        value={row.name}
                        onChange={(e) => updateField(i, { name: e.target.value })}
                        placeholder="nazwa pola (np. data)"
                        className={`${inputClass} min-w-[140px] flex-1`}
                      />
                      <select
                        value={row.baseType}
                        onChange={(e) => updateField(i, { baseType: e.target.value })}
                        className={`${inputClass} w-auto`}
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
                          className={`${inputClass} min-w-[140px] flex-1`}
                        />
                      )}
                      <input
                        type="text"
                        value={row.hint}
                        onChange={(e) => updateField(i, { hint: e.target.value })}
                        placeholder="podpowiedź (opcjonalnie)"
                        className={`${inputClass} min-w-[140px] flex-1`}
                      />
                      <IconButton tone="danger" title="Usuń pole" onClick={() => removeField(i)} className="mt-0.5">
                        <IconClose size={15} />
                      </IconButton>
                    </>
                  )}
                />
              )}
            </div>

            <label className="flex items-center gap-2 text-[13px] text-app-text">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm({ ...form, active: e.target.checked })}
                className="rounded border-app-line text-app-blue"
              />
              Aktywny
            </label>

            <div className="flex justify-end gap-2">
              <Button type="button" onClick={resetForm}>Anuluj</Button>
              <Button type="submit" variant="primary">
                {editingSlug ? 'Zapisz zmiany' : 'Dodaj schemat'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Filtr */}
      <div className="flex items-center justify-end mb-2">
        <label className="flex items-center gap-2 text-[13px] text-app-muted">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            className="rounded border-app-line text-app-blue"
          />
          Pokaż nieaktywne
        </label>
      </div>

      {/* Lista */}
      <Card className="overflow-hidden">
        {loading ? (
          <EmptyState title="Ładowanie…" />
        ) : schemas.length === 0 ? (
          <EmptyState
            title="Brak schematów"
            hint={'Dodaj pierwszy schemat przyciskiem u góry strony.'}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Typ</Th>
                <Th>Pola</Th>
                <Th>Wzorzec nazwy</Th>
                <Th>Status</Th>
                <Th className="text-right">Akcje</Th>
              </tr>
            </thead>
            <tbody>
              {schemas.map((s2) => (
                <tr key={s2.slug} className="group align-top hover:bg-app-hover">
                  <Td>
                    <span className="font-semibold text-app-text">{s2.name}</span>
                    <Sub>{s2.slug}</Sub>
                  </Td>
                  <Td>
                    {(s2.fields || []).length === 0 ? (
                      <span className="text-app-muted">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {s2.fields.map((f) => (
                          <span
                            key={f.name}
                            title={f.type}
                            className="rounded bg-[#f2f4f8] px-2 py-0.5 text-[11px] text-[#65738a]"
                          >
                            {f.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </Td>
                  <Td>
                    {s2.name_pattern ? (
                      <code className="text-[11px] text-app-muted">{s2.name_pattern}</code>
                    ) : (
                      <span className="text-app-muted">—</span>
                    )}
                  </Td>
                  <Td>
                    <Badge tone={s2.active ? 'green' : 'gray'}>
                      {s2.active ? 'Aktywny' : 'Nieaktywny'}
                    </Badge>
                  </Td>
                  <Td>
                    <RowActions>
                      <IconButton tone="edit" title="Edytuj" onClick={() => handleEdit(s2)}>
                        <IconEdit size={16} />
                      </IconButton>
                      <IconButton tone="danger" title="Usuń" onClick={() => handleDelete(s2.slug)}>
                        <IconTrash size={16} />
                      </IconButton>
                    </RowActions>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
