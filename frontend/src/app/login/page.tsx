'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { authApi, versionApi } from '@/lib/api';
import { ustawJezykZKonta } from '@/lib/locale';
import { useAuth } from '@/lib/store';
import { useMarka } from '@/components/marka-provider';
import { LanguageSwitcher } from '@/components/shell/language-switcher';
import { Logo } from '@/components/shell/logo';

export default function LoginPage() {
  const marka = useMarka();
  const t = useTranslations('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [version, setVersion] = useState('');
  const router = useRouter();
  const { login } = useAuth();

  // Aktualna wersja aplikacji (z /api/version) — bez hardkodu
  useEffect(() => {
    versionApi.get().then((d) => { if (d?.version) setVersion(d.version); }).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const data = await authApi.login(email, password);
      login(data.access_token, {
        id: data.user_id,
        email: data.email || email,
        username: data.username || email,
        full_name: data.full_name,
        role: data.role,
        is_active: true,
        is_admin: data.is_admin,
        locale: data.locale ?? null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_login: data.last_login,
      });
      // Konto niosące własny język wymaga PEŁNEGO wejścia na pulpit: teksty ustala
      // układ główny na serwerze, a przy nawigacji klienckiej Next go nie odtwarza.
      if (ustawJezykZKonta(data.locale)) {
        window.location.href = '/dashboard';
        return;
      }
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || t('error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Przełącznik języka JEST tu mimo braku górnej belki: bez niego osoba
            anglojęzyczna musiałaby zalogować się na polskim ekranie, żeby dopiero
            potem przestawić język. Wybór z tego miejsca zostaje na stałe. */}
        <div className="mb-2 flex justify-end">
          <LanguageSwitcher wariant="ciemny" />
        </div>

        {/* Znak instancji — dokładnie ten sam co na szczycie menu bocznego, tylko
            wyśrodkowany i większy. Wspólny komponent, żeby logowanie i aplikacja
            nie rozjechały się przy pierwszej zmianie marki. */}
        <div className="mb-8 text-center">
          <Logo
            ikona={marka.ikona}
            nazwa={marka.nazwa}
            kolorNazwy={marka.naglowek}
            rozmiar={52}
            rozmiarNazwy={36}
            className="justify-center"
          />
          <p className="mt-3 text-slate-300">{marka.opis}</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-xl shadow-xl p-8">
          <h2 className="text-2xl font-bold text-gray-800 mb-6">{t('title')}</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('email')}
              </label>
              <input
                type="email"
                name="username"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder={marka.przykladEmail}
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('password')}
              </label>
              <input
                type="password"
                name="current-password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="••••••••"
                required
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? t('submitting') : t('submit')}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-slate-400 text-sm mt-6">
          {marka.nazwa} {version ? `v${version} ` : ''}&copy; 2026
        </p>
      </div>
    </div>
  );
}