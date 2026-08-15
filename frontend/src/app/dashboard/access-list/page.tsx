'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { foldersApi } from '@/lib/api';
import { useAuth } from '@/lib/store';
import { ROLE_ADMIN, isAdmin as czyAdmin, roleLabel, useRoles, type Role } from '@/lib/roles';
import { RoleDialog, type RoleDialogMode } from '@/components/role-dialogs';

interface AccessItem {
  folder_id: number;
  name: string;
  path: string;
  access_level: string;
  source: string; // 'direct' | 'inherited'
}


const ACCESS_LABELS: Record<string, string> = { read: 'Odczyt', write: 'Zapis' };

export default function AccessListPage() {
  const { user } = useAuth();
  const isAdmin = czyAdmin(user);
  const { roles, refresh: odswiezRole } = useRoles();
  const [data, setData] = useState<Record<string, AccessItem[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [okno, setOkno] = useState<{ mode: RoleDialogMode; role?: Role } | null>(null);
  const [komunikat, setKomunikat] = useState('');

  const wczytajDostepy = useCallback(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }
    foldersApi
      .accessOverview()
      .then((d) => setData(d || {}))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Błąd pobierania listy dostępów'))
      .finally(() => setLoading(false));
  }, [isAdmin]);

  useEffect(() => {
    wczytajDostepy();
  }, [wczytajDostepy]);

  // Po każdej zmianie w słowniku odświeżamy TAKŻE zestawienie dostępów: utworzenie
  // roli z kopią uprawnień i usunięcie roli zmieniają je natychmiast, a tabela
  // pokazująca stan sprzed operacji byłaby myląca akurat tam, gdzie chodzi o audyt.
  const poZmianie = (tekst: string) => {
    setOkno(null);
    setKomunikat(tekst);
    odswiezRole();
    wczytajDostepy();
  };

  if (!isAdmin) {
    return (
      <div className="text-sm text-gray-600">
        Ta strona jest dostępna tylko dla administratora.
      </div>
    );
  }

  // Kolejność ze słownika ról; administratora pomijamy, bo ma pełny dostęp
  // z definicji. Kody obecne w odpowiedzi, a nieznane słownikowi, dokładamy na
  // koniec — lepiej pokazać rolę bez etykiety niż ukryć jej dostępy.
  const kodyZeSlownika = roles.filter((r) => r.code !== ROLE_ADMIN).map((r) => r.code);
  const kody = [
    ...kodyZeSlownika,
    ...Object.keys(data).filter((r) => !kodyZeSlownika.includes(r)),
  ];

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Lista dostępów</h1>
          <p className="text-sm text-gray-500 mt-1">
            Dostęp efektywny każdej roli do folderów (z uwzględnieniem dziedziczenia).
            Administrator ma zawsze pełny dostęp do wszystkiego.
          </p>
        </div>
        <button
          onClick={() => { setKomunikat(''); setOkno({ mode: 'create' }); }}
          className="shrink-0 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Dodaj rolę
        </button>
      </div>

      {komunikat && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {komunikat}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-500">Ładowanie...</div>
      ) : (
        <div className="space-y-6">
          {kody.map((kod) => {
            const items = data[kod] || [];
            const rola = roles.find((r) => r.code === kod);
            return (
              <div key={kod} className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <h2 className="font-semibold text-gray-800">{roleLabel(roles, kod)}</h2>
                    {rola?.is_system && (
                      <span
                        className="rounded-full border border-gray-300 px-2 py-0.5 text-[11px] text-gray-500"
                        title="Rola wbudowana — aplikacja się do niej odwołuje, więc nie można jej usunąć"
                      >
                        rola systemowa
                      </span>
                    )}
                    <span className="text-xs text-gray-400">
                      {items.length === 0 ? 'brak dostępu' : `folderów: ${items.length}`}
                      {rola ? ` · użytkowników: ${rola.users_count}` : ''}
                    </span>
                  </div>
                  {rola && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setKomunikat(''); setOkno({ mode: 'rename', role: rola }); }}
                        className="rounded-md border border-gray-300 px-2.5 py-1 text-xs text-gray-700 hover:bg-white"
                      >
                        Zmień nazwę
                      </button>
                      {rola.is_system ? (
                        <span className="px-2.5 py-1 text-xs text-gray-400">bez usuwania</span>
                      ) : (
                        <button
                          onClick={() => { setKomunikat(''); setOkno({ mode: 'delete', role: rola }); }}
                          className="rounded-md border border-red-200 px-2.5 py-1 text-xs text-red-600 hover:bg-red-50"
                        >
                          Usuń
                        </button>
                      )}
                    </div>
                  )}
                </div>
                {items.length === 0 ? (
                  <div className="px-4 py-4 text-sm text-gray-500">
                    Ta rola nie ma dostępu do żadnego folderu.
                  </div>
                ) : (
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-white">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Folder</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Ścieżka</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Poziom</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Źródło</th>
                        <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Akcja</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {items.map((it) => (
                        <tr key={it.folder_id} className="hover:bg-gray-50">
                          <td className="px-4 py-2 text-sm text-gray-800 font-medium">📁 {it.name}</td>
                          <td className="px-4 py-2 text-sm text-gray-500">{it.path}</td>
                          <td className="px-4 py-2 text-sm">
                            <span
                              className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                it.access_level === 'write'
                                  ? 'bg-blue-100 text-blue-800'
                                  : 'bg-gray-100 text-gray-700'
                              }`}
                            >
                              {ACCESS_LABELS[it.access_level] || it.access_level}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {it.source === 'inherited' ? 'dziedziczony' : 'bezpośredni'}
                          </td>
                          <td className="px-4 py-2 text-sm text-right">
                            <Link
                              href={`/dashboard/files?folder=${it.folder_id}`}
                              className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                            >
                              Otwórz w Plikach →
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}
        </div>
      )}

      {okno && (
        <RoleDialog
          mode={okno.mode}
          role={okno.role}
          roles={roles}
          onClose={() => setOkno(null)}
          onDone={poZmianie}
        />
      )}
    </div>
  );
}
