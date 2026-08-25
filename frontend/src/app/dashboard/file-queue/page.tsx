'use client';

import { IconRefresh } from '@/components/icons';
import { useTranslations } from 'next-intl';
import { Badge, Button, Card, EmptyState, PageHeader, Table, Td, Th, inputClass } from '@/components/ui/primitives';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/store';
import { docSchemasApi } from '@/lib/api';
import { czasLokalny } from '@/lib/czas';
import { isAdmin as czyAdmin } from '@/lib/roles';

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
  doc_type_verified?: boolean;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// Data + godzina i minuty (bez sekund). Przeliczenie UTC → strefa użytkownika
// robi wspólny helper (src/lib/czas.ts) — wcześniej mieszkało to tylko tutaj.
function fmtDateTime(iso: string | null): string {
  return czasLokalny(iso);
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
  const t = useTranslations('queue');
  const tWspolne = useTranslations('common');
  const { user } = useAuth();
  const isAdmin = czyAdmin(user);
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

  // Ręczna korekta kategorii w „Szczegóły pozycji" (#7B-2)
  const [overrideType, setOverrideType] = useState('');
  const [savingOverride, setSavingOverride] = useState(false);
  useEffect(() => {
    setOverrideType(selectedItem?.doc_type || '');
  }, [selectedItem]);

  const saveOverride = async () => {
    if (!selectedItem || !overrideType) return;
    setSavingOverride(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`/api/files/${selectedItem.id}/doc-type`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ doc_type: overrideType }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setSelectedItem({
          ...selectedItem,
          doc_type: data.doc_type,
          doc_fields: data.doc_fields,
          doc_type_verified: true,
        });
        loadQueue(true);
      } else {
        alert(t('errPrefix', { powod: data?.detail || data?.message || res.statusText }));
      }
    } catch {
      alert(t('errSaveCategory'));
    } finally {
      setSavingOverride(false);
    }
  };

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
    if (!confirm(t('confirmRetry'))) return;
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
        const errorMsg = data?.message || data?.detail || t('errRetry');
        alert(t('errPrefix', { powod: errorMsg }));
        loadQueue(); // Refresh to show updated status
      }
    } catch (err) {
      alert(t('errRetryGeneric'));
      loadQueue(); // Refresh to show updated status
    }
  };

  /**
   * Zwolnij plik zablokowany w „Przetwarzanie".
   *
   * Gdy przebieg w n8n umrze w połowie (błąd węzła), nikt nie zawoła callbacka —
   * plik wisi, a dyspozytor nie wyśle następnego, bo pilnuje zasady „1 plik naraz".
   * Watchdog posprząta to sam, ale dopiero po 30 minutach; ten przycisk robi to od ręki.
   */
  const unstickItem = async (itemId: number) => {
    if (!confirm(
      t('confirmForceRetry')
    )) return;
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`/api/processing-queue/${itemId}/retry`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data?.error) {
        alert(t('errPrefix', { powod: data?.message || data?.detail || res.statusText }));
      }
    } catch {
      alert(t('errRelease'));
    } finally {
      loadQueue();
      loadStatusSummary();
    }
  };

  // NARZĘDZIE TESTOWE (strojenie klasyfikacji) — przetwórz od nowa z kasowaniem
  // wektorów. Docelowo do usunięcia razem z przyciskiem w kolumnie Akcje.
  const reparseItem = async (fileId: number) => {
    if (!confirm(t('confirmReprocess'))) return;
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`/api/processing-queue/${fileId}/reparse`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        loadQueue();
        loadStatusSummary();
      } else {
        alert(t('errPrefix', { powod: data?.detail || data?.message || res.statusText }));
        loadQueue();
      }
    } catch {
      alert(t('errRetryGeneric'));
      loadQueue();
    }
  };

  const deleteItem = async (fileId: number) => {
    if (!confirm(t('confirmDelete'))) return;
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
        alert(t('errDeleteWithReason', { powod: errorData?.detail || res.statusText }));
      }
    } catch (err) {
      alert(t('errDelete'));
    }
  };

  // Nazwa statusu POKAZYWANA użytkownikowi. Sama wartość zostaje polska: leży
  // tak w bazie i służy w kodzie do porównań (ponów, przerwij, szczegóły błędu).
  // Nieznany status pokazujemy dosłownie — lepiej surowa wartość niż pusty znaczek.
  const nazwaStatusu = (status: string) =>
    ({
      'W kolejce': t('statusQueued'),
      'Przetwarzanie': t('statusProcessing'),
      'Przetworzono': t('statusDone'),
      'Błąd przetwarzania': t('statusError'),
    })[status] ?? status;

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'W kolejce':
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

  const kafelek = (etykieta: string, wartosc: number, ton: string) => (
    <Card className="p-4">
      <div className={`text-2xl font-bold ${ton}`}>{wartosc}</div>
      <div className="mt-0.5 text-[13px] text-app-muted">{etykieta}</div>
    </Card>
  );

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className={`${inputClass} w-auto`}
            >
              <option value="">{t('allStatuses')}</option>
              {statuses.map((status) => (
                <option key={status} value={status}>{nazwaStatusu(status)}</option>
              ))}
            </select>
            <Button onClick={() => { loadQueue(); loadStatusSummary(); }} disabled={loading}>
              <IconRefresh size={16} />
              {loading ? t('loading') : t('refresh')}
            </Button>
            <label className="flex items-center gap-2 self-center text-[13px] text-app-muted">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded border-app-line text-app-blue"
              />
              {t('autoRefresh')}
            </label>
          </>
        }
      />

      <div>
        {/* Summary Cards - Status Counts */}
        {/* Liczniki statusów. Kolor niesie znaczenie stanu, nie akcję — niebieski
            zostaje przyciskom. */}
        <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-5">
          {kafelek(t('tileQueued'), statusSummary['W kolejce'] || 0, 'text-[#b7791f]')}
          {kafelek(t('tileProcessing'), statusSummary['Przetwarzanie'] || 0, 'text-[#2455cc]')}
          {kafelek(t('tileDone'), statusSummary['Przetworzono'] || 0, 'text-[#148a57]')}
          {kafelek(t('tileErrors'), statusSummary['Błąd przetwarzania'] || 0, 'text-app-danger')}
          {kafelek(t('tileTotal'), queueItems.length, 'text-app-text')}
        </div>

        {/* Table */}
        <Card className="overflow-hidden">
          <Table>
            <thead>
              <tr>
                <Th>{t('colId')}</Th>
                <Th>{t('colFile')}</Th>
                <Th>{t('colCategory')}</Th>
                <Th>{t('colStatus')}</Th>
                <Th>{t('colAdded')}</Th>
                <Th>{t('colDuration')}</Th>
                {isAdmin && <Th>{t('colActions')}</Th>}
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item) => (
                <tr
                  key={item.id}
                  className="cursor-pointer hover:bg-app-hover"
                  onClick={() => setSelectedItem(selectedItem?.id === item.id ? null : item)}
                >
                  <Td className="text-app-muted">#{item.id}</Td>
                  <Td className="max-w-[260px] truncate font-semibold text-app-text"><span title={item.file_name}>{item.file_name}</span></Td>
                  <Td>
                    {item.doc_type ? (
                      <Badge tone="purple">{typeLabel(item.doc_type)}</Badge>
                    ) : (
                      <span className="text-app-muted">—</span>
                    )}
                  </Td>
                  <Td>
                    <span className={`inline-flex items-center rounded-full px-[9px] py-[5px] text-[11px] font-bold ${getStatusClass(item.status)}`}>
                      {nazwaStatusu(item.status)}
                    </span>
                  </Td>
                  <Td className="text-app-muted">{fmtDateTime(item.created_at)}</Td>
                  <Td className="text-app-muted">{fmtDuration(item.processing_seconds)}</Td>
                  {isAdmin && (
                    <Td>
                      <div className="flex flex-wrap gap-1.5">
                        {(item.status === 'Błąd przetwarzania' || item.status === 'W kolejce') && (
                          <button
                            onClick={(e) => { e.stopPropagation(); retryItem(item.id); }}
                            className="rounded-lg px-2 py-1 text-xs font-semibold text-app-blue hover:bg-[#eef4ff]"
                          >
                            {t('retry')}
                          </button>
                        )}
                        {/* Plik wiszący w „Przetwarzanie" (przebieg w n8n umarł bez odpowiedzi)
                            blokuje całą kolejkę do czasu watchdoga. Ten przycisk zwalnia go od ręki. */}
                        {item.status === 'Przetwarzanie' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); unstickItem(item.id); }}
                            className="whitespace-nowrap rounded-lg px-2 py-1 text-xs font-semibold text-[#b7791f] hover:bg-[#fdf6e7]"
                            title={t('forceRetryTitle')}
                          >
                            {t('forceRetry')}
                          </button>
                        )}
                        {/* NARZĘDZIE TESTOWE — reparse z kasowaniem wektorów (do usunięcia po testach) */}
                        {item.status === 'Przetworzono' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); reparseItem(item.id); }}
                            className="whitespace-nowrap rounded-lg px-2 py-1 text-xs font-semibold text-app-purple hover:bg-app-purplebg"
                            title={t('reprocessTitle')}
                          >
                            {t('reprocess')}
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteItem(item.id); }}
                          className="rounded-lg px-2 py-1 text-xs font-semibold text-app-danger hover:bg-app-dangerbg"
                        >
                          {tWspolne('delete')}
                        </button>
                        {item.status === 'Błąd przetwarzania' && item.error_message && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setSelectedItem(item); }}
                            className="rounded-lg px-2 py-1 text-xs font-semibold text-app-danger hover:bg-app-dangerbg"
                          >
                            {t('errorDetails')}
                          </button>
                        )}
                      </div>
                    </Td>
                  )}
                </tr>
              ))}
              {filteredItems.length === 0 && !loading && (
                <tr>
                  <Td colSpan={isAdmin ? 7 : 6} className="py-10 text-center text-app-muted">
                    {t('empty')}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
          {loading && <EmptyState title={t('loading')} />}
        </Card>
      </div>

      {/* Detail Modal */}
      {selectedItem && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-800">{t('itemDetails', { id: selectedItem.id })}</h2>
              <button
                onClick={() => setSelectedItem(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>

            <dl className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <dt className="text-sm text-gray-500">{t('colFile')}</dt>
                <dd className="text-gray-800 font-medium">{selectedItem.file_name}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">{t('colStatus')}</dt>
                <dd className="text-gray-800">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusClass(selectedItem.status)}`}>
                    {nazwaStatusu(selectedItem.status)}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">{t('colCategory')}</dt>
                <dd className="text-gray-800 flex items-center gap-2 flex-wrap">
                  {selectedItem.doc_type ? (
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                      {typeLabel(selectedItem.doc_type)}
                    </span>
                  ) : '—'}
                  {selectedItem.doc_type_verified && (
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800" title={t('manualTitle')}>
                      {t('manualBadge')}
                    </span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">{t('colAdded')}</dt>
                <dd className="text-gray-800">
                  {fmtDateTime(selectedItem.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">{t('colDuration')}</dt>
                <dd className="text-gray-800">
                  {fmtDuration(selectedItem.processing_seconds)}
                </dd>
              </div>
              {selectedItem.started_at && (
                <div>
                  <dt className="text-sm text-gray-500">{t('startedAt')}</dt>
                  <dd className="text-gray-800">
                    {czasLokalny(selectedItem.started_at, { dateStyle: 'short', timeStyle: 'medium' })}
                  </dd>
                </div>
              )}
              {selectedItem.completed_at && (
                <div>
                  <dt className="text-sm text-gray-500">{t('finishedAt')}</dt>
                  <dd className="text-gray-800">
                    {czasLokalny(selectedItem.completed_at, { dateStyle: 'short', timeStyle: 'medium' })}
                  </dd>
                </div>
              )}
            </dl>

            {/* Ręczna korekta kategorii (admin) — ustawia typ i dolicza pola dla niego */}
            {isAdmin && (
              <div className="border border-gray-200 rounded-lg p-4 mb-4">
                <dt className="text-sm font-medium text-gray-700 mb-2">{t('changeCategory')}</dt>
                <div className="flex items-center gap-2">
                  <select
                    value={overrideType}
                    onChange={(e) => setOverrideType(e.target.value)}
                    disabled={savingOverride}
                    className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-md text-sm bg-white"
                  >
                    <option value="">{t('pickType')}</option>
                    {Object.entries(typeNames).map(([slug, name]) => (
                      <option key={slug} value={slug}>{name}</option>
                    ))}
                    <option value="inny">{t('otherType')}</option>
                  </select>
                  <button
                    onClick={saveOverride}
                    disabled={savingOverride || !overrideType || overrideType === selectedItem.doc_type}
                    className="px-3 py-1.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
                  >
                    {savingOverride ? 'Zapisywanie…' : t('saveCategory')}
                  </button>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {t('saveCategoryHint')}
                </p>
              </div>
            )}

            {selectedItem.doc_fields && Object.keys(selectedItem.doc_fields).length > 0 && (
              <div className="border border-gray-200 rounded-lg p-4 mb-4">
                <dt className="text-sm font-medium text-gray-700 mb-2">{t('recognisedFields')}</dt>
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
                <dt className="text-sm font-medium text-red-800 mb-1">{t('error')}</dt>
                <dd className="text-sm text-red-700 whitespace-pre-wrap">{selectedItem.error_message}</dd>
              </div>
            )}

            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setSelectedItem(null)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md"
              >
                {tWspolne('close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
