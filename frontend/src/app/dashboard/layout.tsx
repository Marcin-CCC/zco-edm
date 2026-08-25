'use client';

/** Powłoka aplikacji w layoucie 1.5: menu boczne + górny pasek + górne menu admina.
 *
 * Zwinięcie menu jest zapamiętywane w przeglądarce (`localStorage`), więc wraca
 * przy kolejnym wejściu. Czytamy je w efekcie, a nie przy pierwszym renderze —
 * inaczej serwer wyrenderowałby menu rozwinięte, a przeglądarka zwinięte
 * i React zgłosiłby niezgodność hydratacji.
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { AdminTabs } from '@/components/shell/admin-tabs';
import { Sidebar } from '@/components/shell/sidebar';
import { Topbar } from '@/components/shell/topbar';
import { settingsApi } from '@/lib/api';
import { useAuth } from '@/lib/store';

const KLUCZ_ZWINIETE = 'sidebar_collapsed';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const t = useTranslations('common');
  const [isReady, setIsReady] = useState(false);
  const [zwiniete, setZwiniete] = useState(false);
  const [menuMobilne, setMenuMobilne] = useState(false);
  const { logout, isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    setZwiniete(localStorage.getItem(KLUCZ_ZWINIETE) === '1');
    setIsReady(true);
    if (!isAuthenticated) router.push('/login');
  }, [isAuthenticated, router]);

  const przelaczZwiniecie = () => {
    setZwiniete((v) => {
      localStorage.setItem(KLUCZ_ZWINIETE, v ? '0' : '1');
      return !v;
    });
  };

  // Auto-wylogowanie po bezczynności (czas z ustawień admina, domyślnie 15 min).
  // Główny mechanizm wylogowania; token JWT to tylko absolutny backstop.
  useEffect(() => {
    if (!isAuthenticated) return;
    let timeoutMs = 15 * 60 * 1000;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const doLogout = () => { logout(); router.push('/login'); };
    const reset = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(doLogout, timeoutMs);
    };
    const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'];

    settingsApi.session()
      .then((d) => { if (!cancelled && d?.idle_timeout_minutes) timeoutMs = d.idle_timeout_minutes * 60 * 1000; })
      .catch(() => { /* fallback: 15 min */ })
      .finally(() => {
        if (cancelled) return;
        events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
        reset();
      });

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [isAuthenticated, logout, router]);

  if (!isReady) {
    return <div className="grid min-h-screen place-items-center bg-app-bg text-app-muted">{t('loading')}</div>;
  }

  return (
    // --shell-x = margines po bokach, gdy okno jest szersze niż 1920 px. Menu boczne
    // jest `fixed` (względem okna, nie kontenera), więc zamiast owijać całość
    // w kontener przesuwamy jego krawędź o tę zmienną.
    <div
      className="min-h-screen bg-app-bg text-app-text"
      style={{ ['--shell-x' as string]: 'max(0px, (100vw - 1920px) / 2)' } as React.CSSProperties}
    >
      <Sidebar
        collapsed={zwiniete}
        onToggleCollapsed={przelaczZwiniecie}
        mobileOpen={menuMobilne}
        onCloseMobile={() => setMenuMobilne(false)}
      />

      {/* Margines na menu dokładamy dopiero od `lg` — niżej menu jest wysuwane
          znad treści, więc miejsce po lewej byłoby pustą kolumną. */}
      <div
        className="ml-[var(--shell-x)] mr-[var(--shell-x)] min-h-screen transition-[margin] duration-200 lg:ml-[calc(var(--shell-x)+var(--szer-menu))]"
        style={{
          ['--szer-menu' as string]: zwiniete
            ? 'var(--app-sidebar-w-collapsed)'
            : 'var(--app-sidebar-w)',
        } as React.CSSProperties}
      >
        <Topbar onOpenMobileMenu={() => setMenuMobilne(true)} />
        <main className="px-4 py-5 lg:px-[34px]">
          <AdminTabs />
          {children}
        </main>
      </div>
    </div>
  );
}
