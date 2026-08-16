/** Pozycje nawigacji — jedno źródło dla menu bocznego i górnego menu administracyjnego.
 *
 * Górne menu (`AdminTabs`) powtarza pozycje spod kreski w menu bocznym, z tymi samymi
 * ikonami. Trzymamy je w jednej liście, bo dwie kopie rozjechałyby się przy pierwszej
 * zmianie — a użytkownik ma dwie drogi do tego samego ekranu i musi widzieć to samo.
 */
import type { ComponentType, SVGProps } from 'react';

import {
  IconAccess,
  IconAnswers,
  IconChat,
  IconDashboard,
  IconFiles,
  IconQueue,
  IconSchemas,
  IconSearch,
  IconSettings,
  IconUsers,
} from '@/components/icons';

export interface NavItem {
  label: string;
  href: string;
  Icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  /** Dopasowanie dokładne — inaczej „/dashboard" świeciłoby na każdej podstronie. */
  exact?: boolean;
}

/** Nad kreską — dla wszystkich zalogowanych. */
export const NAV_MAIN: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', Icon: IconDashboard, exact: true },
  { label: 'Pliki', href: '/dashboard/files', Icon: IconFiles },
  { label: 'Chat z AI', href: '/dashboard/chat', Icon: IconChat },
  { label: 'Wyszukiwanie', href: '/dashboard/wyszukiwanie', Icon: IconSearch },
];

/** Pod kreską — wyłącznie dla administratora. */
export const NAV_ADMIN: NavItem[] = [
  { label: 'Użytkownicy', href: '/dashboard/users', Icon: IconUsers },
  { label: 'Lista dostępów', href: '/dashboard/access-list', Icon: IconAccess },
  { label: 'Schematy dokumentów', href: '/dashboard/doc-schemas', Icon: IconSchemas },
  { label: 'Kolejka plików', href: '/dashboard/file-queue', Icon: IconQueue },
  { label: 'Lista odpowiedzi', href: '/dashboard/oceny', Icon: IconAnswers },
  // „Ustawienia”, nie „Ustawienia aplikacji”: w górnym menu administracyjnym sześć
  // pozycji z długimi etykietami przestawało się mieścić i pasek dostawał poziomy
  // suwak. Nagłówek samego ekranu zostaje pełny — tam miejsca nie brakuje.
  { label: 'Ustawienia', href: '/dashboard/settings', Icon: IconSettings },
];

export function isNavActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(item.href + '/');
}
