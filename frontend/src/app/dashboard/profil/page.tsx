'use client';

/**
 * Profil — własne konto zalogowanego użytkownika.
 *
 * Układ: dwie niezależne karty. „Dane konta" przełącza się w tryb edycji w tym
 * samym miejscu (bez okna modalnego), „Hasło" ma osobny formularz. Rozdzielenie
 * jest celowe: zmiana e-maila i zmiana hasła to dwie różne decyzje, a wspólny
 * formularz utrudniałby czytelny komunikat o błędzie.
 *
 * Rola i status są tylko do odczytu — zmienia je administrator w module
 * Użytkownicy. Backend też ich stąd nie przyjmuje, więc to nie jest zabezpieczenie
 * pozorne (interfejs i API mówią to samo).
 */

import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useEffect, useState } from 'react';

import { authApi } from '@/lib/api';
import { useAuth } from '@/lib/store';
import { inicjaly } from '@/lib/user';
import { roleLabel, useRoles } from '@/lib/roles';
import { czasLokalny } from '@/lib/czas';

const MIN_HASLO = 8;

function dataPl(iso?: string | null): string {
  return czasLokalny(iso, { dateStyle: 'long', timeStyle: 'short' });
}

export default function ProfilPage() {
  const t = useTranslations('profile');
  const tWspolne = useTranslations('common');
  const { roles } = useRoles();
  const router = useRouter();
  const { user, setUser, logout } = useAuth();

  // ===== Karta „Dane konta" =====
  const [edycja, setEdycja] = useState(false);
  const [form, setForm] = useState({ username: '', full_name: '', email: '' });
  const [zapisywanie, setZapisywanie] = useState(false);
  const [bladDanych, setBladDanych] = useState('');
  const [zapisano, setZapisano] = useState(false);

  // ===== Karta „Hasło" =====
  const [zmianaHasla, setZmianaHasla] = useState(false);
  const [hasla, setHasla] = useState({ current: '', nowe: '', powtorz: '' });
  const [bladHasla, setBladHasla] = useState('');
  const [hasloZmienione, setHasloZmienione] = useState(false);

  useEffect(() => {
    if (user) {
      setForm({
        username: user.username || '',
        full_name: user.full_name || '',
        email: user.email || '',
      });
    }
  }, [user]);

  const rozpocznijEdycje = () => {
    setBladDanych('');
    setZapisano(false);
    setForm({
      username: user?.username || '',
      full_name: user?.full_name || '',
      email: user?.email || '',
    });
    setEdycja(true);
  };

  const zapiszDane = async () => {
    setBladDanych('');
    setZapisywanie(true);
    try {
      const zaktualizowany = await authApi.updateProfile({
        username: form.username.trim(),
        full_name: form.full_name.trim(),
        email: form.email.trim(),
      });
      // Nagłówek i menu czytają dane z tego samego miejsca, więc odświeżają się same
      setUser({ ...(user as any), ...zaktualizowany });
      setEdycja(false);
      setZapisano(true);
    } catch (e: any) {
      setBladDanych(e?.message || t('errSave'));
    } finally {
      setZapisywanie(false);
    }
  };

  const zmienHaslo = async () => {
    setBladHasla('');
    if (hasla.nowe.length < MIN_HASLO) {
      setBladHasla(t('passwordTooShort', { min: MIN_HASLO }));
      return;
    }
    if (hasla.nowe !== hasla.powtorz) {
      setBladHasla(t('passwordMismatch'));
      return;
    }
    setZapisywanie(true);
    try {
      await authApi.changePassword(hasla.current, hasla.nowe);
      setHasloZmienione(true);
      // Wylogowanie po zmianie hasła: użytkownik od razu sprawdza, czy nowe działa
      setTimeout(() => {
        logout();
        router.push('/login');
      }, 2000);
    } catch (e: any) {
      setBladHasla(e?.message || t('errPassword'));
    } finally {
      setZapisywanie(false);
    }
  };

  if (!user) {
    return <div className="text-gray-500">{t('loading')}</div>;
  }

  const poleKlasy =
    'w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 focus:outline-none ' +
    'focus:ring-2 focus:ring-blue-500 focus:border-transparent';

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">{t('title')}</h1>

      {/* ===================== DANE KONTA ===================== */}
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div className="flex items-center gap-4 min-w-0">
            <div className="w-14 h-14 shrink-0 rounded-full bg-blue-600 text-white flex items-center justify-center text-lg font-semibold">
              {inicjaly(user.full_name, user.username)}
            </div>
            <div className="min-w-0">
              <div className="text-lg font-semibold text-gray-800 break-words">
                {user.full_name || user.username}
              </div>
              <div className="text-sm text-gray-500 break-words">{user.email}</div>
            </div>
          </div>
          {!edycja && (
            <button
              onClick={rozpocznijEdycje}
              className="shrink-0 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
            >
              {t('editData')}
            </button>
          )}
        </div>

        {zapisano && !edycja && (
          <div className="mb-4 px-3 py-2 rounded-md bg-green-50 border border-green-200 text-sm text-green-800">
            {t('saved')}
          </div>
        )}
        {bladDanych && (
          <div className="mb-4 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
            {bladDanych}
          </div>
        )}

        {edycja ? (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1">{t('displayName')}</label>
              <input
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className={poleKlasy}
                autoFocus
              />
              <p className="mt-1 text-xs text-gray-500">
                {t('displayNameHint')}
              </p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">{t('fullName')}</label>
              <input
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className={poleKlasy}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">{t('email')}</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className={poleKlasy}
              />
              <p className="mt-1 text-xs text-gray-500">
                {t('emailHint')}
              </p>
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={zapiszDane}
                disabled={zapisywanie}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                {zapisywanie ? tWspolne('saving') : tWspolne('save')}
              </button>
              <button
                onClick={() => { setEdycja(false); setBladDanych(''); }}
                disabled={zapisywanie}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
              >
                {tWspolne('cancel')}
              </button>
            </div>
          </div>
        ) : (
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <dt className="text-sm text-gray-500">{t('displayName')}</dt>
              <dd className="text-gray-800 font-medium break-words">{user.username}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('fullName')}</dt>
              <dd className="text-gray-800 font-medium break-words">{user.full_name || '—'}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('email')}</dt>
              <dd className="text-gray-800 font-medium break-words">{user.email}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('role')}</dt>
              <dd className="text-gray-800 font-medium">
                {roleLabel(roles, user.role)}
                <span className="ml-2 text-xs text-gray-500">{t('roleHint')}</span>
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('accountStatus')}</dt>
              <dd className="text-gray-800 font-medium">{user.is_active ? t('accountActive') : t('accountInactive')}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('lastLogin')}</dt>
              <dd className="text-gray-800 font-medium">{dataPl(user.last_login)}</dd>
            </div>
          </dl>
        )}
      </div>

      {/* ===================== HASŁO ===================== */}
      <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">{t('password')}</h2>
            <p className="text-sm text-gray-500 mt-1">
              {t('passwordHint')}
            </p>
          </div>
          {!zmianaHasla && !hasloZmienione && (
            <button
              onClick={() => { setZmianaHasla(true); setBladHasla(''); setHasla({ current: '', nowe: '', powtorz: '' }); }}
              className="shrink-0 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
            >
              {t('changePassword')}
            </button>
          )}
        </div>

        {hasloZmienione ? (
          <div className="mt-4 px-3 py-2 rounded-md bg-green-50 border border-green-200 text-sm text-green-800">
            {t('passwordChanged')}
          </div>
        ) : zmianaHasla ? (
          <div className="mt-5 space-y-4">
            {bladHasla && (
              <div className="px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
                {bladHasla}
              </div>
            )}
            <div>
              <label className="block text-sm text-gray-600 mb-1">{t('currentPassword')}</label>
              <input
                type="password"
                autoComplete="current-password"
                value={hasla.current}
                onChange={(e) => setHasla({ ...hasla, current: e.target.value })}
                className={poleKlasy}
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">{t('newPassword')}</label>
              <input
                type="password"
                autoComplete="new-password"
                value={hasla.nowe}
                onChange={(e) => setHasla({ ...hasla, nowe: e.target.value })}
                className={poleKlasy}
              />
              <p className="mt-1 text-xs text-gray-500">{t('passwordMinChars', { min: MIN_HASLO })}</p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">{t('repeatPassword')}</label>
              <input
                type="password"
                autoComplete="new-password"
                value={hasla.powtorz}
                onChange={(e) => setHasla({ ...hasla, powtorz: e.target.value })}
                className={poleKlasy}
              />
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={zmienHaslo}
                disabled={zapisywanie || !hasla.current || !hasla.nowe || !hasla.powtorz}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                {zapisywanie ? t('changingPassword') : t('changePassword')}
              </button>
              <button
                onClick={() => { setZmianaHasla(false); setBladHasla(''); }}
                disabled={zapisywanie}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
              >
                {tWspolne('cancel')}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
