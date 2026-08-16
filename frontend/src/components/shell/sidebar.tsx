'use client';

/** Menu boczne layoutu 1.5.
 *
 * Zwijanie uruchamia kliknięcie w logo (tak jak w makiecie — nie ma osobnej
 * strzałki), a stan jest zapamiętywany między sesjami. Zwinięte menu zostawia
 * same ikony z tooltipami, panel pomocy kurczy się do koła ratunkowego,
 * a stopka do samego znaku ©, który pozostaje odnośnikiem do dostawcy.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

import { IconLifebuoy } from '@/components/icons';
import { useMarka } from '@/components/marka-provider';
import { NAV_ADMIN, NAV_MAIN, isNavActive, type NavItem } from '@/components/shell/nav-items';
import { versionApi } from '@/lib/api';
import { isAdmin as czyAdmin } from '@/lib/roles';
import { useAuth } from '@/lib/store';

interface Props {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** Menu wysunięte na wąskim ekranie (poniżej lg). */
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: Props) {
  const pathname = usePathname();
  const { user } = useAuth();
  const marka = useMarka();
  const [wersja, setWersja] = useState('');

  useEffect(() => {
    versionApi.get().then((d) => setWersja(d?.version || '')).catch(() => setWersja(''));
  }, []);

  const pozycja = (item: NavItem) => {
    const aktywna = isNavActive(pathname, item);
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onCloseMobile}
        title={collapsed ? item.label : undefined}
        aria-current={aktywna ? 'page' : undefined}
        className={[
          'flex items-center gap-3 rounded-[9px] px-[14px] py-3 text-[15px] text-[#f7fbff] transition-colors',
          collapsed ? 'justify-center px-0' : '',
          aktywna
            ? 'bg-gradient-to-r from-[#2377ef] to-[#2b65e8] shadow-[inset_0_0_0_1px_rgba(255,255,255,.08),0_8px_22px_rgba(18,84,182,.28)]'
            : 'hover:bg-white/[.06]',
        ].join(' ')}
      >
        <span className="grid h-5 w-5 flex-none place-items-center">
          <item.Icon size={18} />
        </span>
        {!collapsed && <span className="whitespace-nowrap">{item.label}</span>}
      </Link>
    );
  };

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-20 bg-black/40 lg:hidden" onClick={onCloseMobile} aria-hidden />
      )}
      <aside
        className={[
          'fixed left-[var(--shell-x)] top-0 z-30 flex min-h-screen flex-col text-white transition-[width,padding,transform] duration-200',
          collapsed ? 'w-[72px] px-[10px] py-[18px]' : 'w-[244px] px-[14px] py-[18px]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
        style={{ background: 'var(--app-sidebar)' }}
      >
        {/* Logo przełącza zwijanie — jedyny mechanizm, zgodnie z makietą. */}
        <button
          onClick={onToggleCollapsed}
          title={collapsed ? 'Rozwiń menu' : 'Zwiń menu'}
          aria-label={collapsed ? 'Rozwiń menu' : 'Zwiń menu'}
          className={[
            'mb-5 flex select-none items-center gap-[10px] px-1 pt-1 text-[28px] font-extrabold',
            collapsed ? 'justify-center px-0' : '',
          ].join(' ')}
        >
          <span
            className="relative h-9 w-9 flex-none rounded-[9px] bg-gradient-to-b from-[#2e8bff] to-[#1767dd] shadow-[0_8px_18px_rgba(25,103,221,.3)]"
            aria-hidden
          >
            <span className="absolute left-[10px] top-[15.5px] h-[5px] w-4 rounded-[2px] bg-white" />
            <span className="absolute left-[15.5px] top-[10px] h-4 w-[5px] rounded-[2px] bg-white" />
          </span>
          {!collapsed && (
            <span style={{ color: marka.naglowek }} className="leading-none">
              {marka.nazwa}
            </span>
          )}
        </button>

        <nav className="flex flex-col gap-[6px]">
          {NAV_MAIN.map(pozycja)}
          {czyAdmin(user) && (
            <>
              {/* Kreska z podpisem — dzieli menu na część wspólną i administracyjną.
                  W zwiniętym menu zostaje sama kreska: napis nie zmieściłby się
                  w 72 px, a skrót typu „ADM" niczego nie wyjaśnia. */}
              {collapsed ? (
                <div className="my-[10px] h-px bg-white/[.12]" />
              ) : (
                <div className="my-[10px] flex items-center gap-2.5 px-[14px]">
                  <span className="text-[10px] font-semibold uppercase tracking-[.12em] text-white/40">
                    Administracja
                  </span>
                  <span className="h-px flex-1 bg-white/[.12]" />
                </div>
              )}
              {NAV_ADMIN.map(pozycja)}
            </>
          )}
        </nav>

        <div
          className={[
            'mt-auto rounded-xl border border-white/[.08] bg-white/[.06]',
            collapsed ? 'grid place-items-center p-3' : 'p-4',
          ].join(' ')}
          title="Potrzebujesz pomocy?"
        >
          {collapsed ? (
            <Link href="/dashboard/kontakt" aria-label="Skontaktuj się" className="text-white">
              <IconLifebuoy size={24} />
            </Link>
          ) : (
            <>
              <strong className="mb-1.5 block text-[13px]">Potrzebujesz pomocy?</strong>
              <p className="mb-3.5 text-xs leading-[1.45] text-[#c9d6ea]">
                Skontaktuj się z działem wsparcia technicznego.
              </p>
              <Link
                href="/dashboard/kontakt"
                onClick={onCloseMobile}
                className="block rounded-lg bg-white/10 py-2.5 text-center text-[13px] font-bold text-white hover:bg-white/[.16]"
              >
                Skontaktuj się
              </Link>
            </>
          )}
        </div>

        <div
          className={[
            'mt-[18px] text-xs leading-[1.8] text-[#a9bbd4]',
            collapsed ? 'p-0 text-center' : 'px-1.5',
          ].join(' ')}
        >
          {collapsed ? (
            <a
              href="https://polmedi.com"
              target="_blank"
              rel="noopener noreferrer"
              title="© Polmedi Group sp. z o.o."
              className="text-[15px] hover:text-white"
            >
              ©
            </a>
          ) : (
            <>
              {marka.nazwa} v{wersja || '—'} ·{' '}
              <Link href="/dashboard/changelog" className="hover:text-white">
                Historia zmian
              </Link>
              <br />
              <a
                href="https://polmedi.com"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-white"
              >
                © Polmedi Group sp. z o.o.
              </a>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
