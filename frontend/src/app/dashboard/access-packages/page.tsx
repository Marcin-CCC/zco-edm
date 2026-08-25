'use client';
import { useTranslations } from 'next-intl';

export default function AccessPackagesPage() {
  const t = useTranslations('packages');
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">{t('title')}</h1>
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
        <h3 className="text-lg font-medium text-blue-800 mb-2">{t('soon')}</h3>
        <p className="text-blue-600 text-sm">
          {t('soonText')}
        </p>
      </div>
    </div>
  );
}