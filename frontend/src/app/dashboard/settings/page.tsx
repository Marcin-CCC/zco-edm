'use client';

import { useState, useEffect } from 'react';
import { settingsApi } from '@/lib/api';

export default function SettingsPage() {
  const [webhookUrl, setWebhookUrl] = useState('');
  const [chatWebhookUrl, setChatWebhookUrl] = useState('');
  const [allowedExtensions, setAllowedExtensions] = useState('');
  const [idleTimeout, setIdleTimeout] = useState('15');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await settingsApi.get();
      setWebhookUrl(data.n8n_webhook_url || '');
      setChatWebhookUrl(data.chat_webhook_url || '');
      setAllowedExtensions(data.allowed_extensions || '');
      setIdleTimeout(String(data.idle_timeout_minutes ?? 15));
    } catch (err: any) {
      setMessage({ type: 'error', text: 'Nie udało się załadować ustawień' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    setError('');

    try {
      await settingsApi.update({ n8n_webhook_url: webhookUrl });
      if (chatWebhookUrl.trim()) {
        await settingsApi.updateChatWebhook({ chat_webhook_url: chatWebhookUrl });
      }
      if (allowedExtensions.trim()) {
        await settingsApi.updateAllowedExtensions({ allowed_extensions: allowedExtensions });
      }
      const it = parseInt(idleTimeout, 10);
      if (!Number.isNaN(it)) {
        await settingsApi.updateIdleTimeout({ idle_timeout_minutes: it });
      }
      setMessage({ type: 'success', text: 'Ustawienia zapisane pomyślnie' });
      // Odśwież — pokaż wartości po normalizacji z backendu
      await loadSettings();
    } catch (err: any) {
      const detail = err.message || 'Nie udało się zapisać ustawień';
      setError(detail);
      setMessage(null);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-gray-500">Ładowanie...</div>;
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Ustawienia aplikacji</h1>

      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Adres webhooka do przetwarzania plików
          </label>
          <input
            type="text"
            value={webhookUrl}
            onChange={(e) => {
              setWebhookUrl(e.target.value);
              setError('');
            }}
            className={`w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              error ? 'border-red-500' : 'border-gray-300'
            }`}
            placeholder="http://localhost:5678/webhook/document-uploaded"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Adres webhooka czatu
          </label>
          <input
            type="text"
            value={chatWebhookUrl}
            onChange={(e) => {
              setChatWebhookUrl(e.target.value);
              setError('');
            }}
            className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="https://n8n-host/webhook/xxxx/chat"
          />
          <p className="mt-1 text-xs text-gray-500">
            URL triggera &quot;When chat message received&quot; z workflow czatu n8n (tryb streaming).
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Dozwolone rozszerzenia plików
          </label>
          <input
            type="text"
            value={allowedExtensions}
            onChange={(e) => {
              setAllowedExtensions(e.target.value);
              setError('');
            }}
            className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="pdf,docx,xlsx"
          />
          <p className="mt-1 text-xs text-gray-500">
            Lista rozdzielona przecinkami. Musi odpowiadać typom obsługiwanym przez workflow n8n
            (gałęzie &quot;Switch on file ext&quot;) — inaczej plik zostanie przyjęty, ale nie przetworzony.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Auto-wylogowanie po bezczynności (minuty)
          </label>
          <input
            type="number"
            min={1}
            max={1440}
            value={idleTimeout}
            onChange={(e) => {
              setIdleTimeout(e.target.value);
              setError('');
            }}
            className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="15"
          />
          <p className="mt-1 text-xs text-gray-500">
            Po tylu minutach bez aktywności użytkownik zostanie wylogowany i wróci na ekran logowania
            (od 1 do 1440 min). Niezależnie od tego sesja ma twardy limit 12 godzin.
          </p>
        </div>

        {error && (
          <p className="text-sm text-red-600">{error}</p>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? 'Zapisywanie...' : 'Zapisz'}
        </button>

        {message && (
          <div
            className={`p-4 rounded-md ${
              message.type === 'success'
                ? 'bg-green-50 text-green-800 border border-green-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
}
