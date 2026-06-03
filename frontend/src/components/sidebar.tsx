import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/store';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

interface NavItem {
  label: string;
  href: string;
  roles: string[];
  exact?: boolean;
  children?: string[];  // paths that should activate this menu item
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', roles: ['admin', 'doctor', 'medical_staff', 'technician', 'office_staff', 'guest'], exact: true },
  { label: 'Pliki', href: '/dashboard/files', roles: ['admin', 'doctor', 'medical_staff', 'technician', 'office_staff', 'guest'], exact: true },
  { label: 'Administracja', href: '/dashboard/users', roles: ['admin'], children: ['/dashboard/users', '/dashboard/access-packages', '/dashboard/file-queue'] },
];

function isActive(pathname: string, item: NavItem): boolean {
  // Exact match
  if (item.exact) {
    return pathname === item.href;
  }
  // Check if pathname is under any of the child paths
  if (item.children) {
    for (const child of item.children) {
      if (pathname === child || pathname.startsWith(child + '/')) {
        return true;
      }
    }
  }
  // Default: check if pathname starts with href
  return pathname === item.href || pathname.startsWith(item.href + '/');
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();
  const userRole = user?.role || '';

  // Filter menu items based on user role
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(userRole));

  return (
    <>
      {/* Overlay mobile */}
      {isOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed top-0 left-0 z-50 h-full w-64 bg-slate-900 text-white transition-transform duration-300 lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo / Title */}
        <div className="flex items-center justify-between px-4 py-5 border-b border-slate-700">
          <h1 className="text-xl font-bold">EDM ZCO</h1>
          <button onClick={onClose} className="lg:hidden text-white text-xl">&times;</button>
        </div>

        {/* Navigation - only main items, no submenus */}
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
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-700">
          <p className="text-xs text-slate-400">EDM ZCO v1.0.0</p>
        </div>
      </aside>
    </>
  );
}