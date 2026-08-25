'use client';

/** Górny pasek layoutu 1.5.
 *
 * Makieta ma po lewej globalną wyszukiwarkę (⌘K), a przy awatarze dzwonek
 * powiadomień z licznikiem. Obu tu NIE MA — decyzja z 2026-08-16: żadna z tych
 * funkcji nie istnieje jeszcze w aplikacji, a pasek wyszukiwania, który nic nie
 * znajduje, i licznik pokazujący „3" bez treści są gorsze niż ich brak.
 * Wracamy do nich, gdy powstanie wyszukiwanie globalne i kanał powiadomień.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useEffect, useRef, useState } from 'react';

import { IconChevronDown, IconMenu } from '@/components/icons';
import { LanguageSwitcher } from '@/components/shell/language-switcher';
import { roleLabel, useRoles } from '@/lib/roles';
import { useAuth } from '@/lib/store';
import { inicjaly } from '@/lib/user';

export function Topbar({ onOpenMobileMenu }: { onOpenMobileMenu: () => void }) {
  const { user, logout } = useAuth();
  const { roles } = useRoles();
  const t = useTranslations('shell');
  const pathname = usePathname();
  const [otwarte, setOtwarte] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => setOtwarte(false), [pathname]);

  useEffect(() => {
    if (!otwarte) return;
    const poza = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOtwarte(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOtwarte(false); };
    document.addEventListener('mousedown', poza);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', poza);
      document.removeEventListener('keydown', esc);
    };
  }, [otwarte]);

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-app-line bg-white px-4 lg:px-[34px]">
      <button
        onClick={onOpenMobileMenu}
        className="rounded-ctl p-2 text-app-text hover:bg-app-hover lg:hidden"
        aria-label={t('openMenu')}
      >
        <IconMenu size={22} />
      </button>
      <div className="hidden lg:block" />

      <div className="flex items-center gap-1">
        <LanguageSwitcher />

        <div className="relative flex items-center gap-3.5" ref={menuRef}>
          <button
            onClick={() => setOtwarte((v) => !v)}
            className="flex items-center gap-3.5 rounded-ctl px-1 py-1 hover:bg-app-hover"
            aria-haspopup="menu"
            aria-expanded={otwarte}
          >
            <span className="grid h-[38px] w-[38px] flex-none place-items-center rounded-full bg-app-blue font-bold text-white">
              {inicjaly(user?.full_name, user?.username)}
            </span>
            <span className="hidden text-left leading-tight sm:block">
              <strong className="block text-sm text-app-text">{user?.full_name || user?.username}</strong>
              <span className="text-xs text-app-muted">{roleLabel(roles, user?.role)}</span>
            </span>
            <IconChevronDown size={16} className="text-app-muted" />
          </button>

          {otwarte && (
            <div
              role="menu"
              className="absolute right-0 top-[52px] w-52 rounded-xl border border-app-line bg-white py-1 shadow-card"
            >
              <div className="border-b border-app-line px-3 py-2">
                <div className="truncate text-sm font-medium text-app-text">
                  {user?.full_name || user?.username}
                </div>
                <div className="truncate text-xs text-app-muted">{user?.email}</div>
              </div>
              <Link href="/dashboard/profil" role="menuitem" className="block px-3 py-2 text-sm text-app-text hover:bg-app-hover">
                {t('profile')}
              </Link>
              {/* „Instrukcja", nie „Pomoc" — pomoc w menu bocznym prowadzi do kontaktu
                  ze wsparciem i dwie pozycje o tej samej nazwie myliły użytkowników. */}
              <Link href="/dashboard/pomoc" role="menuitem" className="block px-3 py-2 text-sm text-app-text hover:bg-app-hover">
                {t('manual')}
              </Link>
              <button
                onClick={() => { setOtwarte(false); logout(); }}
                role="menuitem"
                className="block w-full px-3 py-2 text-left text-sm text-app-danger hover:bg-app-hover"
              >
                {t('logout')}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
