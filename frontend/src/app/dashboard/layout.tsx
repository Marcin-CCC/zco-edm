'use client';

import { useState, useEffect } from 'react';
import { Sidebar } from '@/components/sidebar';
import { useAuth } from '@/lib/store';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';

interface SubMenuItem {
  label: string;
  href: string;
}

// Submenu tabs for admin pages
const ADMIN_SUBMENU: SubMenuItem[] = [
  { label: 'Użytkownicy', href: '/dashboard/users' },
  { label: 'Pakiety praw', href: '/dashboard/access-packages' },
  { label: 'Kolejka plików', href: '/dashboard/file-queue' },
  { label: 'Ustawienia aplikacji', href: '/dashboard/settings' },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + '/');
}

// Which pages should show tabs
const PAGES_WITH_TABS: string[] = ['/dashboard/users', '/dashboard/access-packages', '/dashboard/file-queue', '/dashboard/settings'];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isReady, setIsReady] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
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

  if (!isReady) {
    return <div className="min-h-screen bg-gray-100 flex items-center justify-center">Ładowanie...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Hamburger button for mobile */}
      <button
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        className="fixed top-3 left-3 z-50 p-2 bg-slate-900 text-white rounded-md lg:hidden"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <Sidebar isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />

      {/* Top bar */}
      <header className={`fixed top-0 left-0 right-0 z-30 bg-white shadow-sm ${showTabs ? 'lg:left-[256px]' : 'lg:left-64'}`}>
        {/* User info row */}
        <div className={`flex items-center justify-end px-4 gap-4 ${showTabs ? 'h-10' : 'h-12'}`}>
          <span className="text-sm text-gray-600">
            Witaj, <span className="font-medium text-gray-800">{user?.username}</span>
          </span>
          <button
            onClick={logout}
            className="px-4 py-1 text-xs font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors"
          >
            Wyloguj
          </button>
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
      <main className={`pt-[56px] ${showTabs ? 'lg:pt-[96px]' : 'lg:pt-[72px]'} ${showTabs ? 'lg:ml-[256px]' : 'lg:ml-64'}`}>
        <div className="p-4 lg:p-6">
          {children}
        </div>
      </main>
    </div>
  );
}