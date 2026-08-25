'use client';

import { useTranslations } from 'next-intl';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/store';
import { useMarka } from '@/components/marka-provider';

export default function RootPage() {
  const t = useTranslations('common');
  const marka = useMarka();
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated) {
      router.push('/dashboard');
    } else {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  // Ekran przelotowy: widać go ułamek sekundy przed przekierowaniem. Stała tu
  // plakietka „GitHub Actions CI/CD Active" i podpis „Wdrozenie przez GitHub
  // Actions - TEST" — rusztowanie z czasu stawiania wdrożenia, pokazywane
  // użytkownikom. Zostaje sama nazwa instancji.
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      <div className="text-center text-white">
        <h1 className="mb-2 text-4xl font-bold">{marka.nazwa}</h1>
        <p className="text-slate-300">{t('loading')}</p>
      </div>
    </div>
  );
}