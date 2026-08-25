'use client';

/**
 * Okna zarządzania rolami (dodanie, zmiana nazwy, usunięcie).
 *
 * Wydzielone z podstrony „Lista dostępów", bo trzy okna z własnym stanem,
 * walidacją i obsługą błędów przytłoczyłyby tabelę dostępów, która jest
 * właściwą treścią tamtego ekranu.
 *
 * Zasady, które okna mają egzekwować (pełne uzasadnienie w app/roles/router.py):
 * - kod roli jest niezmienny — zmieniamy wyłącznie etykietę,
 * - roli systemowej nie da się usunąć,
 * - usunięcie roli z użytkownikami wymaga wskazania, dokąd ich przenieść.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { rolesApi } from '@/lib/api';
import { codeFromName, type Role } from '@/lib/roles';

export type RoleDialogMode = 'create' | 'rename' | 'delete';

/** UWAGA: funkcja zna WYŁĄCZNIE polskie reguły. Liczebniki widoczne w oknach
 *  przeszły na komunikaty ICU; ta zostaje bez wołających i czeka na usunięcie.
 *
 *  Polska odmiana rzeczownika po liczbie: 1 osoby / 3 osób / 5 osób.
 *
 * Bez tego okno pokazuje „1 uprawnień", co w oknie potwierdzającym operację
 * nieodwracalną wygląda po prostu na niedokończone.
 */
function odmiana(n: number, formy: [string, string, string]): string {
  if (n === 1) return formy[0];
  const dziesiatki = n % 100;
  const jednosci = n % 10;
  if (jednosci >= 2 && jednosci <= 4 && !(dziesiatki >= 12 && dziesiatki <= 14)) return formy[1];
  return formy[2];
}

interface Props {
  mode: RoleDialogMode;
  /** Rola, której dotyczy okno (dla 'rename' i 'delete'). */
  role?: Role | null;
  /** Cały słownik — potrzebny na listy wyboru (skąd skopiować, dokąd przenieść). */
  roles: Role[];
  onClose: () => void;
  /** Wywoływane po udanej zmianie; strona odświeża słownik i zestawienie dostępów. */
  onDone: (komunikat: string) => void;
}

function Okno({ tytul, children, stopka }: {
  tytul: string;
  children: React.ReactNode;
  stopka: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-lg">
        <div className="px-5 pt-5">
          <h2 className="text-lg font-semibold text-gray-800">{tytul}</h2>
        </div>
        <div className="px-5 py-4 space-y-3">{children}</div>
        <div className="flex justify-end gap-2 border-t border-gray-100 px-5 py-3">{stopka}</div>
      </div>
    </div>
  );
}

export function RoleDialog({ mode, role, roles, onClose, onDone }: Props) {
  const t = useTranslations('roles');
  const tWspolne = useTranslations('common');
  const [nazwa, setNazwa] = useState(mode === 'rename' ? role?.name || '' : '');
  const [kopiujZ, setKopiujZ] = useState('');
  const [przeniesDo, setPrzeniesDo] = useState('');
  const [blad, setBlad] = useState('');
  const [zapisywanie, setZapisywanie] = useState(false);
  const poleNazwy = useRef<HTMLInputElement>(null);

  useEffect(() => {
    poleNazwy.current?.focus();
    const naKlawisz = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', naKlawisz);
    return () => window.removeEventListener('keydown', naKlawisz);
  }, [onClose]);

  // Domyślny cel przeniesienia: pierwsza inna rola. Bez wstępnego wyboru
  // administrator mógłby kliknąć „Przenieś i usuń" z pustą listą i dostać błąd
  // z serwera zamiast działającego okna.
  const inneRole = roles.filter((r) => r.code !== role?.code);
  useEffect(() => {
    if (mode === 'delete' && !przeniesDo && inneRole.length) setPrzeniesDo(inneRole[0].code);
  }, [mode, przeniesDo, inneRole]);

  async function wykonaj() {
    setBlad('');
    setZapisywanie(true);
    try {
      if (mode === 'create') {
        const utworzona = await rolesApi.create({
          name: nazwa.trim(),
          copy_permissions_from: kopiujZ || null,
        });
        onDone(t('created', { name: utworzona.name, code: utworzona.code }));
      } else if (mode === 'rename') {
        const zmieniona = await rolesApi.rename(role!.code, nazwa.trim());
        onDone(t('renamed', { name: zmieniona.name }));
      } else {
        const trzebaPrzeniesc = (role?.users_count || 0) > 0;
        const wynik = await rolesApi.remove(role!.code, trzebaPrzeniesc ? przeniesDo : null);
        const przeniesieni = wynik.users_moved ? t('moved', { count: wynik.users_moved }) : '';
        onDone(t('removed', { name: role!.name }) + przeniesieni);
      }
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : t('errGeneric'));
      setZapisywanie(false);
    }
  }

  const przyciskAnuluj = (
    <button
      onClick={onClose}
      className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
    >
      {tWspolne('cancel')}
    </button>
  );

  const komunikatBledu = blad && (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {blad}
    </div>
  );

  if (mode === 'delete') {
    const uzytkownicy = role?.users_count || 0;
    const uprawnienia = role?.permissions_count || 0;
    return (
      <Okno
        tytul={t('deleteTitle', { name: role?.name ?? '' })}
        stopka={
          <>
            {przyciskAnuluj}
            <button
              onClick={wykonaj}
              disabled={zapisywanie || (uzytkownicy > 0 && !przeniesDo)}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {uzytkownicy > 0 ? t('moveAndDelete') : t('deleteRole')}
            </button>
          </>
        }
      >
        {komunikatBledu}
        {uzytkownicy > 0 ? (
          <>
            <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {t.rich('assignedTo', { count: uzytkownicy, b: (c) => <strong>{c}</strong> })}
              {uprawnienia > 0 && t.rich('andHasPerms', { count: uprawnienia, b: (c) => <strong>{c}</strong> })}.
            </div>
            <label className="block text-sm text-gray-600">
              {t('moveUsersTo')}
              <select
                value={przeniesDo}
                onChange={(e) => setPrzeniesDo(e.target.value)}
                className="mt-1 w-full rounded-md border border-gray-300 p-2 text-sm text-gray-800"
              >
                {inneRole.map((r) => (
                  <option key={r.code} value={r.code}>{r.name}</option>
                ))}
              </select>
            </label>
          </>
        ) : (
          <p className="text-sm text-gray-600">
            {t('nobodyAssigned')}
            {uprawnienia > 0 && t.rich('butHasPerms', { count: uprawnienia, b: (c) => <strong>{c}</strong> })}.
          </p>
        )}
        <p className="text-xs text-gray-500">
          {t('permsWarning')}
        </p>
      </Okno>
    );
  }

  const kod = codeFromName(nazwa);
  const tytul = mode === 'create' ? t('newRole') : t('renameTitle', { name: role?.name ?? '' });

  return (
    <Okno
      tytul={tytul}
      stopka={
        <>
          {przyciskAnuluj}
          <button
            onClick={wykonaj}
            disabled={zapisywanie || nazwa.trim().length < 2 || (mode === 'create' && !kod)}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {mode === 'create' ? t('createRole') : t('saveName')}
          </button>
        </>
      }
    >
      {komunikatBledu}
      <label className="block text-sm text-gray-600">
        {t('roleName')}
        <input
          ref={poleNazwy}
          value={nazwa}
          onChange={(e) => setNazwa(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && nazwa.trim().length >= 2 && !zapisywanie) wykonaj();
          }}
          maxLength={100}
          placeholder={t('namePlaceholder')}
          className="mt-1 w-full rounded-md border border-gray-300 p-2 text-sm text-gray-800"
        />
      </label>

      {mode === 'create' ? (
        <>
          <p className="text-xs text-gray-500">
            {kod ? (
              t.rich('codeInfo', { code: () => <span className="font-mono">{kod}</span> })
            ) : (
              t('nameNeedsChars')
            )}
          </p>
          <label className="block text-sm text-gray-600">
            {t('copyFrom')}
            <select
              value={kopiujZ}
              onChange={(e) => setKopiujZ(e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 p-2 text-sm text-gray-800"
            >
              <option value="">{t('startEmpty')}</option>
              {roles.map((r) => (
                <option key={r.code} value={r.code}>{r.name}</option>
              ))}
            </select>
          </label>
          <p className="text-xs text-gray-500">
            {t('noPermsHint')}
          </p>
        </>
      ) : (
        <p className="text-xs text-gray-500">
          {t.rich('renameHint', { code: () => <span className="font-mono">{role?.code}</span> })}
        </p>
      )}
    </Okno>
  );
}
