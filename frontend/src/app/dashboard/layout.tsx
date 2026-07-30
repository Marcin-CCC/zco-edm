'use client';

import { useState, useEffect, useRef } from 'react';
import { Sidebar } from '@/components/sidebar';
import { inicjaly } from '@/lib/user';
import { useAuth } from '@/lib/store';
import { settingsApi } from '@/lib/api';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';

interface SubMenuItem {
  label: string;
  href: string;
}

// Submenu tabs for admin pages
const ADMIN_SUBMENU: SubMenuItem[] = [
  { label: 'Użytkownicy', href: '/dashboard/users' },
  { label: 'Lista dostępów', href: '/dashboard/access-list' },
  { label: 'Schematy dokumentów', href: '/dashboard/doc-schemas' },
  { label: 'Kolejka plików', href: '/dashboard/file-queue' },
  { label: 'Ustawienia aplikacji', href: '/dashboard/settings' },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + '/');
}

// Which pages should show tabs
const PAGES_WITH_TABS: string[] = ['/dashboard/users', '/dashboard/access-list', '/dashboard/doc-schemas', '/dashboard/file-queue', '/dashboard/settings'];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isReady, setIsReady] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [menuOtwarte, setMenuOtwarte] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { user, logout, isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const isAdmin = user?.role === 'admin';

  // Show tabs only on specific admin pages
  const showTabs = isAdmin && PAGES_WITH_TABS.some((p) => pathname === p || pathname.startsWith(p + '/'));

  useEffect(() => {
    setIsReady(true);
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  // Menu użytkownika zamyka się kliknięciem poza nim, klawiszem Escape oraz przy
  // przejściu na inną stronę — inaczej zostawałoby otwarte nad nową treścią.
  useEffect(() => {
    if (!menuOtwarte) return;
    const pozaMenu = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOtwarte(false);
    };
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOtwarte(false); };
    document.addEventListener('mousedown', pozaMenu);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', pozaMenu);
      document.removeEventListener('keydown', escape);
    };
  }, [menuOtwarte]);

  useEffect(() => { setMenuOtwarte(false); }, [pathname]);

  // Auto-wylogowanie po bezczynności (czas z ustawień admina, domyślnie 15 min).
  // Główny mechanizm wylogowania; token JWT to tylko absolutny backstop.
  useEffect(() => {
    if (!isAuthenticated) return;
    let timeoutMs = 15 * 60 * 1000;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const doLogout = () => {
      logout();
      router.push('/login');
    };
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
    return <div className="min-h-screen bg-gray-100 flex items-center justify-center">Ładowanie...</div>;
  }

  return (
    // --shell-x = margines po bokach, gdy okno jest szersze niż 1920 px. Sidebar i górny
    // pasek są `fixed` (względem okna, nie kontenera), więc zamiast owijać je w kontener
    // przesuwamy ich krawędzie o tę zmienną — dzięki temu CAŁY interfejs (z paskiem)
    // ma najwyżej 1920 px i jest wyśrodkowany.
    <div
      className="min-h-screen bg-gray-100"
      style={{ ['--shell-x' as string]: 'max(0px, (100vw - 1920px) / 2)' } as React.CSSProperties}
    >
      {/* Hamburger button for mobile */}
      <button
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        className="fixed top-3 left-3 z-50 p-2 bg-[#1d2a4d] text-white rounded-md lg:hidden"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <Sidebar isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />

      {/* Top bar */}
      <header className="fixed top-0 left-[var(--shell-x)] right-[var(--shell-x)] z-30 bg-white shadow-sm lg:left-[calc(var(--shell-x)+256px)]">
        {/* User info row */}
        <div className={`flex items-center justify-end px-4 gap-3 ${showTabs ? 'h-10' : 'h-12'}`}>
          <span className="text-sm text-gray-600">
            Witaj, <span className="font-medium text-gray-800">{user?.username}</span>
          </span>
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOtwarte((v) => !v)}
              className="w-8 h-8 rounded-full bg-blue-600 text-white text-xs font-semibold flex items-center justify-center hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors"
              title="Menu użytkownika"
              aria-haspopup="menu"
              aria-expanded={menuOtwarte}
            >
              {inicjaly(user?.full_name, user?.username)}
            </button>
            {menuOtwarte && (
              <div
                role="menu"
                className="absolute right-0 mt-2 w-44 bg-white rounded-md shadow-lg border border-gray-200 py-1 z-50"
              >
                <div className="px-3 py-2 border-b border-gray-100">
                  <div className="text-sm font-medium text-gray-800 truncate">
                    {user?.full_name || user?.username}
                  </div>
                  <div className="text-xs text-gray-500 truncate">{user?.email}</div>
                </div>
                <Link
                  href="/dashboard/profil"
                  onClick={() => setMenuOtwarte(false)}
                  role="menuitem"
                  className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Profil
                </Link>
                <button
                  onClick={() => { setMenuOtwarte(false); logout(); }}
                  role="menuitem"
                  className="block w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-gray-100"
                >
                  Wyloguj
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Horizontal submenu tabs for admin pages */}
        {showTabs && (
          <div className="h-10 bg-slate-100 border-t border-gray-200 flex items-center px-4 gap-1 overflow-x-auto">
            {ADMIN_SUBMENU.map((item) => {
              const isActiveItem = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-4 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap ${
                    isActiveItem
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        )}
      </header>

      {/* Main content - adjust padding based on whether tabs are shown */}
      <main className={`pt-[56px] ${showTabs ? 'lg:pt-[96px]' : 'lg:pt-[72px]'} ml-[var(--shell-x)] mr-[var(--shell-x)] lg:ml-[calc(var(--shell-x)+256px)]`}>
        {/* Górny padding zredukowany (lg:pt-1) — mniejszy odstęp nad nagłówkiem,
            jednolity na wszystkich stronach; jednocześnie zgadza się z wysokością
            h-[calc(100vh-100px)] strony Chat (72+4+24=100), więc Chat się nie przewija. */}
        <div className="p-4 lg:px-6 lg:pt-1 lg:pb-6">
          {children}
        </div>
      </main>
    </div>
  );
}