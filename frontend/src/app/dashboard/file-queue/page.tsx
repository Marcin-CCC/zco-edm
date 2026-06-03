'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/store';

interface QueueItem {
  id: number;
  document_id: number | null;
  file_name: string;
  status: string;
  page_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

interface Document {
  id: number;
  filename: string;
  status: string;
  created_at: string;
  document_pages: QueueItem[];
}

export default function FileQueuePage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [selectedItem, setSelectedItem] = useState<QueueItem | null>(null);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/processing-queue/' +
        (filterStatus ? `?status=${filterStatus}` : '') +
        '&skip=0&limit=200'
      );
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

  const retryItem = async (itemId: number) => {
    if (!confirm('Czy na pewno ponowić przetwarzanie?')) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/processing-queue/${itemId}/retry`, {
        method: 'POST',
      });
      if (res.ok) {
        loadQueue();
      } else {
        alert('Ponowne przetwarzanie nie powiodło się.');
      }
    } catch (err) {
      alert('Błąd podczas ponownego przetwarzania.');
    }
  };

  const skipPageItem = async (itemId: number, pageNum: number) => {
    if (!confirm(`Pominąć stronę ${pageNum}?`)) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/processing-queue/${itemId}/skip-page`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_number: pageNum }),
      });
      if (res.ok) {
        loadQueue();
      }
    } catch (err) {
      alert('Błąd.');
    }
  };

  // Search
  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'W kolejce (n8n)':
        return 'bg-yellow-100 text-yellow-800';
      case 'W trakcie przetwarzania':
        return 'bg-blue-100 text-blue-800';
      case 'Przetworzono':
        return 'bg-green-100 text-green-800';
      case 'Błąd przetwarzania':
        return 'bg-red-100 text-red-800';
      case 'Pominięto':
        return 'bg-gray-100 text-gray-800';
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
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-800 mb-3">Kolejka plików</h1>
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
            onClick={loadQueue}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 text-sm"
            disabled={loading}
          >
            {loading ? 'Ładowanie...' : '🔄 Odśwież'}
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-yellow-800">
              {queueItems.filter(i => i.status === 'W kolejce (n8n)').length}
            </div>
            <div className="text-sm text-yellow-600">W kolejce</div>
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-blue-800">
              {queueItems.filter(i => i.status === 'W trakcie przetwarzania').length}
            </div>
            <div className="text-sm text-blue-600">W trakcie</div>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-green-800">
              {queueItems.filter(i => i.status === 'Przetworzono').length}
            </div>
            <div className="text-sm text-green-600">Przetworzone</div>
          </div>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-red-800">
              {queueItems.filter(i => i.status === 'Błąd przetwarzania').length}
            </div>
            <div className="text-sm text-red-600">Błędy</div>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plik</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Strony</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data dodania</th>
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
                  <td className="px-4 py-3 text-sm font-medium text-gray-800">{item.file_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{item.page_count}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusClass(item.status)}`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {new Date(item.created_at).toLocaleDateString('pl-PL')}
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
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
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
                <dt className="text-sm text-gray-500">Strony</dt>
                <dd className="text-gray-800">{selectedItem.page_count}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Data dodania</dt>
                <dd className="text-gray-800">
                  {new Date(selectedItem.created_at).toLocaleString('pl-PL')}
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