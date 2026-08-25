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
  IconGlobe,
  IconSchemas,
  IconSearch,
  IconSettings,
  IconUsers,
} from '@/components/icons';

export interface NavItem {
  /** Klucz w katalogu `nav`, nie gotowy napis: lista jest stałą modułu, a napis
   *  musi iść za językiem. Tłumaczą go oba menu, każde swoim `useTranslations`. */
  labelKey: string;
  href: string;
  Icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  /** Dopasowanie dokładne — inaczej „/dashboard" świeciłoby na każdej podstronie. */
  exact?: boolean;
}

/** Nad kreską — dla wszystkich zalogowanych. */
export const NAV_MAIN: NavItem[] = [
  { labelKey: 'dashboard', href: '/dashboard', Icon: IconDashboard, exact: true },
  { labelKey: 'files', href: '/dashboard/files', Icon: IconFiles },
  { labelKey: 'chat', href: '/dashboard/chat', Icon: IconChat },
  { labelKey: 'search', href: '/dashboard/wyszukiwanie', Icon: IconSearch },
];

/** Pod kreską — wyłącznie dla administratora. */
export const NAV_ADMIN: NavItem[] = [
  { labelKey: 'users', href: '/dashboard/users', Icon: IconUsers },
  { labelKey: 'accessList', href: '/dashboard/access-list', Icon: IconAccess },
  { labelKey: 'docSchemas', href: '/dashboard/doc-schemas', Icon: IconSchemas },
  { labelKey: 'fileQueue', href: '/dashboard/file-queue', Icon: IconQueue },
  { labelKey: 'answers', href: '/dashboard/oceny', Icon: IconAnswers },
  { labelKey: 'languages', href: '/dashboard/languages', Icon: IconGlobe },
  // „Ustawienia”, nie „Ustawienia aplikacji”: w górnym menu administracyjnym sześć
  // pozycji z długimi etykietami przestawało się mieścić i pasek dostawał poziomy
  // suwak. Nagłówek samego ekranu zostaje pełny — tam miejsca nie brakuje.
  { labelKey: 'settings', href: '/dashboard/settings', Icon: IconSettings },
];

export function isNavActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(item.href + '/');
}
