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
import { useEffect, useState } from 'react';

import { authApi } from '@/lib/api';
import { useAuth } from '@/lib/store';
import { ROLE_LABELS, inicjaly } from '@/lib/user';
import { czasLokalny } from '@/lib/czas';

const MIN_HASLO = 8;

function dataPl(iso?: string | null): string {
  return czasLokalny(iso, { dateStyle: 'long', timeStyle: 'short' });
}

export default function ProfilPage() {
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
      setBladDanych(e?.message || 'Nie udało się zapisać zmian.');
    } finally {
      setZapisywanie(false);
    }
  };

  const zmienHaslo = async () => {
    setBladHasla('');
    if (hasla.nowe.length < MIN_HASLO) {
      setBladHasla(`Nowe hasło musi mieć co najmniej ${MIN_HASLO} znaków.`);
      return;
    }
    if (hasla.nowe !== hasla.powtorz) {
      setBladHasla('Powtórzone hasło różni się od nowego.');
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
      setBladHasla(e?.message || 'Nie udało się zmienić hasła.');
    } finally {
      setZapisywanie(false);
    }
  };

  if (!user) {
    return <div className="text-gray-500">Wczytywanie danych konta…</div>;
  }

  const poleKlasy =
    'w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 focus:outline-none ' +
    'focus:ring-2 focus:ring-blue-500 focus:border-transparent';

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Profil</h1>

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
              Edytuj dane
            </button>
          )}
        </div>

        {zapisano && !edycja && (
          <div className="mb-4 px-3 py-2 rounded-md bg-green-50 border border-green-200 text-sm text-green-800">
            Zmiany zostały zapisane.
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
              <label className="block text-sm text-gray-600 mb-1">Nazwa wyświetlana</label>
              <input
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className={poleKlasy}
                autoFocus
              />
              <p className="mt-1 text-xs text-gray-500">
                Widoczna w nagłówku i w zestawieniach. Nie służy do logowania, więc
                możesz ją zmieniać dowolnie.
              </p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Imię i nazwisko</label>
              <input
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className={poleKlasy}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Adres e-mail</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className={poleKlasy}
              />
              <p className="mt-1 text-xs text-gray-500">
                Tym adresem logujesz się do aplikacji.
              </p>
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={zapiszDane}
                disabled={zapisywanie}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                {zapisywanie ? 'Zapisywanie…' : 'Zapisz'}
              </button>
              <button
                onClick={() => { setEdycja(false); setBladDanych(''); }}
                disabled={zapisywanie}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
              >
                Anuluj
              </button>
            </div>
          </div>
        ) : (
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <dt className="text-sm text-gray-500">Nazwa wyświetlana</dt>
              <dd className="text-gray-800 font-medium break-words">{user.username}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Imię i nazwisko</dt>
              <dd className="text-gray-800 font-medium break-words">{user.full_name || '—'}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Adres e-mail</dt>
              <dd className="text-gray-800 font-medium break-words">{user.email}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Rola</dt>
              <dd className="text-gray-800 font-medium">
                {ROLE_LABELS[user.role] || user.role}
                <span className="ml-2 text-xs text-gray-500">(zmienia administrator)</span>
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Status konta</dt>
              <dd className="text-gray-800 font-medium">{user.is_active ? 'Aktywne' : 'Nieaktywne'}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Ostatnie logowanie</dt>
              <dd className="text-gray-800 font-medium">{dataPl(user.last_login)}</dd>
            </div>
          </dl>
        )}
      </div>

      {/* ===================== HASŁO ===================== */}
      <div className="mt-6 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">Hasło</h2>
            <p className="text-sm text-gray-500 mt-1">
              Do zmiany hasła potrzebne jest hasło obecnie używane.
            </p>
          </div>
          {!zmianaHasla && !hasloZmienione && (
            <button
              onClick={() => { setZmianaHasla(true); setBladHasla(''); setHasla({ current: '', nowe: '', powtorz: '' }); }}
              className="shrink-0 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
            >
              Zmień hasło
            </button>
          )}
        </div>

        {hasloZmienione ? (
          <div className="mt-4 px-3 py-2 rounded-md bg-green-50 border border-green-200 text-sm text-green-800">
            Hasło zostało zmienione. Za chwilę nastąpi wylogowanie — zaloguj się nowym hasłem.
          </div>
        ) : zmianaHasla ? (
          <div className="mt-5 space-y-4">
            {bladHasla && (
              <div className="px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
                {bladHasla}
              </div>
            )}
            <div>
              <label className="block text-sm text-gray-600 mb-1">Aktualne hasło</label>
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
              <label className="block text-sm text-gray-600 mb-1">Nowe hasło</label>
              <input
                type="password"
                autoComplete="new-password"
                value={hasla.nowe}
                onChange={(e) => setHasla({ ...hasla, nowe: e.target.value })}
                className={poleKlasy}
              />
              <p className="mt-1 text-xs text-gray-500">Co najmniej {MIN_HASLO} znaków.</p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Powtórz nowe hasło</label>
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
                {zapisywanie ? 'Zmienianie…' : 'Zmień hasło'}
              </button>
              <button
                onClick={() => { setZmianaHasla(false); setBladHasla(''); }}
                disabled={zapisywanie}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
              >
                Anuluj
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
