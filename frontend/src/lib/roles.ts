/** Słownik ról — jedno źródło prawdy dla całego interfejsu.
 *
 * Do wersji 1.0.21 role były wypisane na sztywno w sześciu miejscach frontu
 * (etykiety, listy wyboru, kolejność, filtr menu). Administrator może teraz
 * zakładać własne, więc każda taka lista byłaby natychmiast nieaktualna —
 * a rola, której nie ma na liście, znika z interfejsu razem z możliwością
 * zarządzania nią.
 */
'use client';

import { useCallback, useEffect, useState } from 'react';

export interface Role {
  code: string;
  name: string;
  is_system: boolean;
  sort_order: number;
  users_count: number;
  permissions_count: number;
}

export const ROLE_ADMIN = 'ADMIN';
export const ROLE_GUEST = 'GUEST';

/** Czy użytkownik jest administratorem.
 *
 * Porównanie bez względu na wielkość liter jest tu konieczne, a nie
 * elegancją: do 1.0.21 API zwracało `admin`, od 1.1.0 zwraca `ADMIN`, a osoby
 * zalogowane w chwili wdrożenia mają starą postać zapisaną w przeglądarce.
 * Bez tego straciłyby widok administratora aż do ponownego logowania.
 */
export function isAdmin(user?: { role?: string | null } | null): boolean {
  return (user?.role || '').toUpperCase() === ROLE_ADMIN;
}

/** Etykieta roli do pokazania człowiekowi; gdy słownik jeszcze nie dojechał,
 * pokazujemy kod — lepszy kod niż puste miejsce. */
export function roleLabel(roles: Role[], code?: string | null): string {
  if (!code) return '';
  const found = roles.find((r) => r.code.toUpperCase() === code.toUpperCase());
  return found ? found.name : code;
}

const POLISH_LETTERS: Record<string, string> = {
  ą: 'a', ć: 'c', ę: 'e', ł: 'l', ń: 'n', ó: 'o', ś: 's', ź: 'z', ż: 'z',
};

/** Podgląd kodu, jaki nada roli backend: „Pielęgniarka" → „PIELEGNIARKA".
 *
 * Świadome powtórzenie `code_from_name` z `app/roles/service.py`. Rozstrzyga
 * backend (to on rozwiązuje kolizje sufiksem `_2`), a to jest wyłącznie podgląd
 * dla administratora — kod jest niezmienny po utworzeniu, więc lepiej, żeby
 * zobaczył go PRZED kliknięciem, niż odkrywał po fakcie.
 */
export function codeFromName(name: string): string {
  const base = (name || '')
    .trim()
    .toLowerCase()
    .replace(/[ąćęłńóśźż]/g, (c) => POLISH_LETTERS[c] || c)
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return base.toUpperCase().slice(0, 50);
}

// Słownik zmienia się rzadko, a potrzebuje go kilka ekranów naraz. Trzymamy więc
// jedną kopię na moduł i jedno zapytanie w locie — inaczej wejście na stronę
// z trzema komponentami czytającymi role wysyłałoby trzy takie same żądania.
let cache: Role[] | null = null;
let inFlight: Promise<Role[]> | null = null;

async function fetchRoles(): Promise<Role[]> {
  const { rolesApi } = await import('@/lib/api');
  return rolesApi.list();
}

export function invalidateRoles(): void {
  cache = null;
  inFlight = null;
}

export function useRoles() {
  const [roles, setRoles] = useState<Role[]>(cache || []);
  const [loading, setLoading] = useState(cache === null);
  const [error, setError] = useState('');

  const load = useCallback(async (force = false) => {
    if (force) invalidateRoles();
    if (cache) {
      setRoles(cache);
      setLoading(false);
      return cache;
    }
    setLoading(true);
    try {
      inFlight = inFlight || fetchRoles();
      const data = await inFlight;
      cache = data;
      setRoles(data);
      setError('');
      return data;
    } catch (e: unknown) {
      inFlight = null;
      setError(e instanceof Error ? e.message : 'Nie udało się pobrać listy ról');
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { roles, loading, error, refresh: () => load(true) };
}
