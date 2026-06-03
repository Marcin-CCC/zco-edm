'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/store';
import { dashboardApi } from '@/lib/api';

export default function DashboardPage() {
  const { user } = useAuth();

  const [stats, setStats] = useState({ users: 0, documents: 0, folders: 0, processed: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await dashboardApi.stats();
        setStats({
          users: data.users ?? 0,
          documents: data.documents ?? 0,
          folders: data.folders ?? 0,
          processed: data.processed ?? 0,
        });
      } catch (err: any) {
        setError(err.message || 'Nie udało się załadować statystyk');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  const statItems = [
    { label: 'Użytkownicy', value: String(stats.users), href: '/dashboard/users' },
    { label: 'Dokumenty', value: String(stats.documents), href: '#' },
    { label: 'Foldery', value: String(stats.folders), href: '#' },
    { label: 'Przetworzone', value: String(stats.processed), href: '#' },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>

      {/* Error */}
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {statItems.map((stat) => (
          <a
            key={stat.label}
            href={stat.href}
            className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow"
          >
            <p className="text-sm text-gray-500">{stat.label}</p>
            <p className="text-2xl font-bold text-gray-800">
              {loading ? '...' : stat.value}
            </p>
          </a>
        ))}
      </div>

      {/* User info */}
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Twoje konto</h2>
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <dt className="text-sm text-gray-500">Użytkownik</dt>
            <dd className="text-gray-800 font-medium">{user?.username}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Email</dt>
            <dd className="text-gray-800 font-medium">{user?.email}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Rola</dt>
            <dd className="text-gray-800 font-medium capitalize">{user?.role}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Status</dt>
            <dd className="text-gray-800 font-medium">
              {user?.is_active ? 'Aktywny' : 'Nieaktywny'}
            </dd>
          </div>
        </dl>
      </div>

      {/* Coming soon */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
        <h3 className="text-lg font-medium text-blue-800 mb-2">Wkrótce</h3>
        <p className="text-blue-600 text-sm">
          Moduły dokumentów, folderów i RAG będą dostępne w następnej aktualizacji.
        </p>
      </div>
    </div>
  );
}