'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { foldersApi } from '@/lib/api';
import { useAuth } from '@/lib/store';

interface AccessItem {
  folder_id: number;
  name: string;
  path: string;
  access_level: string;
  source: string; // 'direct' | 'inherited'
}

const ROLE_LABELS: Record<string, string> = {
  doctor: 'Lekarz',
  medical_staff: 'Personel medyczny',
  technician: 'Technik',
  office_staff: 'Personel biurowy',
  guest: 'Gość',
};
// Kolejność wyświetlania ról
const ROLE_ORDER = ['doctor', 'medical_staff', 'technician', 'office_staff', 'guest'];

const ACCESS_LABELS: Record<string, string> = { read: 'Odczyt', write: 'Zapis' };

export default function AccessListPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [data, setData] = useState<Record<string, AccessItem[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
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

  if (!isAdmin) {
    return (
      <div className="text-sm text-gray-600">
        Ta strona jest dostępna tylko dla administratora.
      </div>
    );
  }

  // Role do pokazania: znane w kolejności + ewentualne nieznane z odpowiedzi
  const roles = [
    ...ROLE_ORDER.filter((r) => r in data),
    ...Object.keys(data).filter((r) => !ROLE_ORDER.includes(r)),
  ];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Lista dostępów</h1>
        <p className="text-sm text-gray-500 mt-1">
          Dostęp efektywny każdej roli do folderów (z uwzględnieniem dziedziczenia).
          Administrator ma zawsze pełny dostęp do wszystkiego.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-500">Ładowanie...</div>
      ) : (
        <div className="space-y-6">
          {roles.map((role) => {
            const items = data[role] || [];
            return (
              <div key={role} className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                  <h2 className="font-semibold text-gray-800">
                    {ROLE_LABELS[role] || role}
                  </h2>
                  <span className="text-xs text-gray-400">
                    {items.length === 0 ? 'brak dostępu' : `folderów: ${items.length}`}
                  </span>
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
    </div>
  );
}
