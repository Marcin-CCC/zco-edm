'use client';

import { useState, useEffect } from 'react';
import { settingsApi } from '@/lib/api';

export default function SettingsPage() {
  const [webhookUrl, setWebhookUrl] = useState('');
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
      setMessage({ type: 'success', text: 'Ustawienia zapisane pomyślnie' });
    } catch (err: any) {
      const detail = err.message || 'Nie udało się zapisać ustawień';
      setError(detail);
      setMessage(null);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-6">Ładowanie...</div>;
  }

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Ustawienia aplikacji</h1>

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
          {error && (
            <p className="mt-1 text-sm text-red-600">{error}</p>
          )}
        </div>

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
