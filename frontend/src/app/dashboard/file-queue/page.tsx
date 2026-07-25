'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/store';
import { docSchemasApi } from '@/lib/api';

interface QueueItem {
  id: number;
  document_id: number | null;
  file_name: string;
  status: string;
  page_count: number;
  error_message: string | null;
  processing_seconds: number | null;
  doc_type?: string | null;
  doc_fields?: Record<string, string> | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// Backend zapisuje czas w UTC bez strefy — dołóż 'Z', by przeglądarka przeliczyła
// na czas lokalny (inaczej pokazałaby wartość UTC jako lokalną).
function parseUtc(iso: string): Date {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : iso + 'Z');
}

// Data + godzina i minuty (bez sekund)
function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  return parseUtc(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' });
}

// Czas parsowania w formacie "X min Y s" / "Y s"
function fmtDuration(sec: number | null | undefined): string {
  if (sec == null) return '—';
  const total = Math.round(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m} min ${s} s` : `${s} s`;
}

export default function FileQueuePage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [selectedItem, setSelectedItem] = useState<QueueItem | null>(null);
  const [statusSummary, setStatusSummary] = useState<Record<string, number>>({});
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [typeNames, setTypeNames] = useState<Record<string, string>>({});

  // Mapowanie slug → nazwa typu (do kolumny „Kategoria"); włącznie z nieaktywnymi,
  // bo dokument mógł zostać sklasyfikowany typem później wyłączonym.
  useEffect(() => {
    docSchemasApi.list(true)
      .then((rows) => setTypeNames(Object.fromEntries(rows.map((s) => [s.slug, s.name]))))
      .catch(() => { /* brak rejestru = pokażemy sam slug */ });
  }, []);

  const typeLabel = (slug?: string | null) => (slug ? (typeNames[slug] || slug) : null);

  // silent=true → odświeżanie w tle (polling), bez migotania spinnera
  const loadQueue = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const params = new URLSearchParams();
      if (filterStatus) params.append('status', filterStatus);
      params.append('skip', '0');
      params.append('limit', '500');
      
      const res = await fetch(`/api/files/queue?${params.toString()}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setQueueItems(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error('Failed to load queue:', err);
    } finally {
      setLoading(false);
    }
  }, [filterStatus]);

  const loadStatusSummary = useCallback(async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/files/status-summary', {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setStatusSummary(data || {});
      }
    } catch (err) {
      console.error('Failed to load status summary:', err);
    }
  }, []);

  useEffect(() => {
    loadQueue();
    loadStatusSummary();
  }, [loadQueue, loadStatusSummary]);

  // Auto-odświeżanie w locie (polling co 5 s), gdy włączone
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => {
      loadQueue(true);
      loadStatusSummary();
    }, 5000);
    return () => clearInterval(id);
  }, [autoRefresh, loadQueue, loadStatusSummary]);

  const retryItem = async (itemId: number) => {
    if (!confirm('Czy na pewno ponowić przetwarzanie?')) return;
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`/api/processing-queue/${itemId}/retry`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && !data.error) {
        loadQueue();
      } else {
        const errorMsg = data?.message || data?.detail || 'Ponowne przetwarzanie nie powiodło się.';
        alert(`Błąd: ${errorMsg}`);
        loadQueue(); // Refresh to show updated status
      }
    } catch (err) {
      alert('Błąd podczas ponownego przetwarzania.');
      loadQueue(); // Refresh to show updated status
    }
  };

  const deleteItem = async (fileId: number) => {
    if (!confirm('Czy na pewno usunąć ten plik?')) return;
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`/api/files/${fileId}`, {
        method: 'DELETE',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      if (res.ok || res.status === 200) {
        loadQueue();
        loadStatusSummary();
      } else {
        const errorData = await res.json().catch(() => ({}));
        alert(`Usunięcie nie powiodło się: ${errorData?.detail || res.statusText}`);
      }
    } catch (err) {
      alert('Usunięcie nie powiodło się.');
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'W kolejce (n8n)':
        return 'bg-yellow-100 text-yellow-800';
      case 'Przetwarzanie':
        return 'bg-blue-100 text-blue-800';
      case 'Przetworzono':
        return 'bg-green-100 text-green-800';
      case 'Błąd przetwarzania':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const filteredItems = filterStatus
    ? queueItems.filter(item => item.status === filterStatus)
    : queueItems;

  const statuses = [...new Set(queueItems.map(item => item.status))];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Nagłówek strony (wzorzec jak Dashboard) */}
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Kolejka plików</h1>

      {/* Moduł: filtry i odświeżanie (bez nagłówka → niższy) */}
      <div className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center space-x-3">
          {/* Status filter */}
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-1 text-sm"
          >
            <option value="">Wszystkie statusy</option>
            {statuses.map(status => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
          <button
            onClick={() => { loadQueue(); loadStatusSummary(); }}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 text-sm"
            disabled={loading}
          >
            {loading ? 'Ładowanie...' : '🔄 Odśwież'}
          </button>
          <label className="flex items-center gap-2 text-sm text-gray-600 ml-1">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            Auto-odświeżanie (5 s)
          </label>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Summary Cards - Status Counts */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-yellow-800">
              {statusSummary['W kolejce (n8n)'] || 0}
            </div>
            <div className="text-sm text-yellow-600">W kolejce (n8n)</div>
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-blue-800">
              {statusSummary['Przetwarzanie'] || 0}
            </div>
            <div className="text-sm text-blue-600">Przetwarzanie</div>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-green-800">
              {statusSummary['Przetworzono'] || 0}
            </div>
            <div className="text-sm text-green-600">Przetworzone</div>
          </div>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-red-800">
              {statusSummary['Błąd przetwarzania'] || 0}
            </div>
            <div className="text-sm text-red-600">Błędy</div>
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-gray-800">
              {queueItems.length}
            </div>
            <div className="text-sm text-gray-600">Łącznie</div>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase w-[30%]">Plik</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Kategoria</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data dodania</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Czas parsowania</th>
                {isAdmin && <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Akcje</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredItems.map((item) => (
                <tr
                  key={item.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => setSelectedItem(selectedItem?.id === item.id ? null : item)}
                >
                  <td className="px-4 py-3 text-sm text-gray-600">#{item.id}</td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-800 max-w-[220px] truncate" title={item.file_name}>{item.file_name}</td>
                  <td className="px-4 py-3">
                    {item.doc_type ? (
                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                        {typeLabel(item.doc_type)}
                      </span>
                    ) : (
                      <span className="text-gray-400 text-sm">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusClass(item.status)}`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {fmtDateTime(item.created_at)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {fmtDuration(item.processing_seconds)}
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3">
                      <div className="flex space-x-2">
                        {(item.status === 'Błąd przetwarzania' || item.status === 'W kolejce (n8n)') && (
                          <button
                            onClick={(e) => { e.stopPropagation(); retryItem(item.id); }}
                            className="text-blue-600 hover:text-blue-800 text-sm"
                          >
                            🔄 Ponów
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteItem(item.id); }}
                          className="text-red-600 hover:text-red-800 text-sm"
                        >
                          🗑️ Usuń
                        </button>
                        {item.status === 'Błąd przetwarzania' && item.error_message && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setSelectedItem(item); }}
                            className="text-red-600 hover:text-red-800 text-sm"
                          >
                            ℹ️ Details
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {filteredItems.length === 0 && !loading && (
                <tr>
                  <td colSpan={isAdmin ? 7 : 6} className="px-4 py-8 text-center text-gray-500">
                    Brak pozycji w kolejce
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {loading && (
            <div className="px-4 py-8 text-center text-gray-500">Ładowanie...</div>
          )}
        </div>
      </div>

      {/* Detail Modal */}
      {selectedItem && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-800">Szczegóły pozycji #{selectedItem.id}</h2>
              <button
                onClick={() => setSelectedItem(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>

            <dl className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <dt className="text-sm text-gray-500">Plik</dt>
                <dd className="text-gray-800 font-medium">{selectedItem.file_name}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Status</dt>
                <dd className="text-gray-800">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusClass(selectedItem.status)}`}>
                    {selectedItem.status}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Kategoria</dt>
                <dd className="text-gray-800">
                  {selectedItem.doc_type ? (
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                      {typeLabel(selectedItem.doc_type)}
                    </span>
                  ) : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Data dodania</dt>
                <dd className="text-gray-800">
                  {fmtDateTime(selectedItem.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Czas parsowania</dt>
                <dd className="text-gray-800">
                  {fmtDuration(selectedItem.processing_seconds)}
                </dd>
              </div>
              {selectedItem.started_at && (
                <div>
                  <dt className="text-sm text-gray-500">Rozpoczęto</dt>
                  <dd className="text-gray-800">
                    {new Date(selectedItem.started_at).toLocaleString('pl-PL')}
                  </dd>
                </div>
              )}
              {selectedItem.completed_at && (
                <div>
                  <dt className="text-sm text-gray-500">Zakończono</dt>
                  <dd className="text-gray-800">
                    {new Date(selectedItem.completed_at).toLocaleString('pl-PL')}
                  </dd>
                </div>
              )}
            </dl>

            {selectedItem.doc_fields && Object.keys(selectedItem.doc_fields).length > 0 && (
              <div className="border border-gray-200 rounded-lg p-4 mb-4">
                <dt className="text-sm font-medium text-gray-700 mb-2">Rozpoznane pola</dt>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
                  {Object.entries(selectedItem.doc_fields).map(([k, v]) => (
                    <div key={k} className="text-sm">
                      <dt className="text-gray-500">{k}</dt>
                      <dd className="text-gray-800 break-words">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}

            {selectedItem.error_message && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                <dt className="text-sm font-medium text-red-800 mb-1">Błąd</dt>
                <dd className="text-sm text-red-700 whitespace-pre-wrap">{selectedItem.error_message}</dd>
              </div>
            )}

            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setSelectedItem(null)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
              >
                Zamknij
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
