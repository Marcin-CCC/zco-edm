'use client';

/** Górne menu administracyjne — druga droga między ekranami spod kreski.
 *
 * Pozycje i ikony bierze z tej samej listy co menu boczne (`NAV_ADMIN`), więc
 * nie da się zmienić jednego bez drugiego. Stan „bieżąca strona" oznaczamy
 * jasnym tłem i niebieskim tekstem, nie niebieskim wypełnieniem — niebieski
 * jest w tym layoucie zarezerwowany dla akcji.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { NAV_ADMIN, isNavActive } from '@/components/shell/nav-items';

export function AdminTabs() {
  const pathname = usePathname();
  const naEkranieAdmina = NAV_ADMIN.some((item) => isNavActive(pathname, item));
  if (!naEkranieAdmina) return null;

  return (
    // `flex-wrap`, nie `overflow-x-auto`: przy ciasnym ekranie zakładki schodzą do
    // drugiego wiersza, zamiast chować się pod poziomym suwakiem. Ukryta zakładka to
    // ukryta droga do ekranu, a suwaka nad menu nawigacyjnym nikt tam nie szuka.
    <nav className="mb-[22px] flex flex-wrap gap-1 rounded-xl border border-app-line bg-white p-1.5">
      {NAV_ADMIN.map((item) => {
        const aktywna = isNavActive(pathname, item);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={aktywna ? 'page' : undefined}
            className={[
              'flex items-center gap-2 whitespace-nowrap rounded-[9px] px-[13px] py-[9px] text-[13px] font-semibold transition-colors',
              aktywna ? 'bg-[#edf4ff] font-bold text-app-blue' : 'text-[#5d6d86] hover:bg-[#f2f6fd] hover:text-app-text',
            ].join(' ')}
          >
            <span className="grid h-[18px] w-[18px] flex-none place-items-center">
              <item.Icon size={18} />
            </span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
