import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/store';
import { versionApi } from '@/lib/api';
import { useMarka } from '@/components/marka-provider';
import { useEffect, useState } from 'react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

interface NavItem {
  label: string;
  href: string;
  roles: string[];
  exact?: boolean;
  children?: string[];
}
const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', roles: ['admin', 'doctor', 'medical_staff', 'technician', 'office_staff', 'guest'], exact: true },
  { label: 'Pliki', href: '/dashboard/files', roles: ['admin', 'doctor', 'medical_staff', 'technician', 'office_staff', 'guest'], exact: true },
  { label: 'Baza wiedzy', href: '/dashboard/chat', roles: ['admin', 'doctor', 'medical_staff', 'technician', 'office_staff', 'guest'], exact: true },
  { label: 'Administracja', href: '/dashboard/users', roles: ['admin'], children: ['/dashboard/users', '/dashboard/access-list', '/dashboard/doc-schemas', '/dashboard/file-queue', '/dashboard/settings', '/dashboard/oceny'] },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) {
    return pathname === item.href;
  }
  if (item.children) {
    for (const child of item.children) {
      if (pathname === child || pathname.startsWith(child + '/')) {
        return true;
      }
    }
  }
  return pathname === item.href || pathname.startsWith(item.href + '/');
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();
  const marka = useMarka();
  const userRole = user?.role || '';
  const [version, setVersion] = useState('');

  useEffect(() => {
    versionApi.get().then((data) => {
      if (data && data.version) {
        setVersion(data.version);
      }
    }).catch(() => {
      setVersion('1.0.0');
    });
  }, []);

  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(userRole));

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed top-0 left-[var(--shell-x)] z-50 h-full w-64 bg-[var(--marka-tlo)] text-white transition-transform duration-300 lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-4 py-5 border-b border-white/10">
          <h1 className="text-xl font-bold text-[var(--marka-naglowek)]">{marka.nazwa}</h1>
          <button onClick={onClose} className="lg:hidden text-white text-xl">&times;</button>
        </div>

        <nav className="mt-4">
          {visibleItems.map((item) => {
            const isActiveItem = isActive(pathname, item);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={`block px-4 py-3 mx-2 rounded-md text-sm font-medium transition-colors ${
                  isActiveItem
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-white/10 hover:text-white'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-white/10">
          <Link
            href="/dashboard/changelog"
            onClick={onClose}
            className="block text-xs text-slate-400 hover:text-white transition-colors"
            title="Historia zmian"
          >
            {marka.nazwa} v{version} · Historia zmian
          </Link>
          <a
            href="https://polmedi.com"
            target="_blank"
            rel="noopener noreferrer"
            className="block mt-1 text-xs text-slate-400 hover:text-white transition-colors"
            title="Polmedi Group sp. z o.o."
          >
            © Polmedi Group sp. z o.o.
          </a>
        </div>
      </aside>
    </>
  );
}