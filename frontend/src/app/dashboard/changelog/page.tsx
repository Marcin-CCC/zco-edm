'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { versionApi } from '@/lib/api';

interface ChangelogEntry {
  version: string;
  date: string;
  title?: string;
  changes: string[];
}

export default function ChangelogPage() {
  const t = useTranslations('changelog');
  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    versionApi
      .changelog()
      .then((d) => setEntries(d?.entries || []))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : t('errFetch')))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">{t('title')}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {t('description')}
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-500">{t('loading')}</div>
      ) : entries.length === 0 ? (
        <div className="text-sm text-gray-500">{t('empty')}</div>
      ) : (
        <ol className="space-y-6">
          {entries.map((e, idx) => (
            <li
              key={e.version}
              className="bg-white rounded-lg shadow-sm border border-gray-200 p-5"
            >
              <div className="flex items-baseline gap-3 mb-3">
                <span className="text-lg font-bold text-gray-800">v{e.version}</span>
                {idx === 0 && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    {t('current')}
                  </span>
                )}
                <span className="text-sm text-gray-400 ml-auto">{e.date}</span>
              </div>
              {e.title && (
                <p className="text-sm font-medium text-gray-700 mb-2">{e.title}</p>
              )}
              <ul className="list-disc list-inside space-y-1 text-sm text-gray-600">
                {e.changes.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
