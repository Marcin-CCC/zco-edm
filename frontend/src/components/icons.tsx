/** Ikony interfejsu — jedno źródło dla całej aplikacji.
 *
 * Wszystkie pochodzą wprost z makiet 1.5: styl Lucide, `stroke:currentColor`,
 * `stroke-width` 1.7–1.8, `fill:none`. Żadnych glifów unicode w roli ikony.
 *
 * Po co jeden moduł: te same ikony noszą pozycje menu bocznego I górnego menu
 * administracyjnego. Gdyby każdy komponent rysował własne, wystarczyłaby jedna
 * poprawka w jednym miejscu, żeby oba menu przestały do siebie pasować.
 */
import type { SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: Props & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function IconDashboard(p: Props) {
  return (
    <Svg {...p}>
      <rect x="3" y="3" width="7" height="9" />
      <rect x="14" y="3" width="7" height="5" />
      <rect x="14" y="12" width="7" height="9" />
      <rect x="3" y="16" width="7" height="5" />
    </Svg>
  );
}

export function IconFiles(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 20V5a1 1 0 0 1 1-1h5l2 2.5h7a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
    </Svg>
  );
}

export function IconChat(p: Props) {
  return (
    <Svg {...p}>
      <path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z" />
      <path d="M8.5 9.5h7M8.5 12.5h4" />
    </Svg>
  );
}

export function IconSearch(p: Props) {
  return (
    <Svg {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="M16.2 16.2L21 21" />
    </Svg>
  );
}

export function IconUsers(p: Props) {
  return (
    <Svg {...p}>
      <path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="3.2" />
      <path d="M22 20v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 4.13A4 4 0 0 1 16 11.6" />
    </Svg>
  );
}

export function IconAccess(p: Props) {
  return (
    <Svg {...p}>
      <rect x="2.5" y="5" width="19" height="14" />
      <circle cx="8.5" cy="10.8" r="2.2" />
      <path d="M5 16.2c.6-1.5 2-2.3 3.5-2.3s2.9.8 3.5 2.3" />
      <path d="M15 10h4M15 13.5h4" />
    </Svg>
  );
}

export function IconSchemas(p: Props) {
  return (
    <Svg {...p}>
      <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z" />
      <path d="M14 3v4h4" />
      <path d="M9 12h6M9 16h4" />
    </Svg>
  );
}

export function IconQueue(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 7h16M4 12h16M4 17h9" />
      <path d="M17 15.5v5M14.5 18h5" />
    </Svg>
  );
}

export function IconAnswers(p: Props) {
  return (
    <Svg {...p}>
      <path d="M20 14a2 2 0 0 1-2 2H9l-4 3.5V5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2z" />
      <path d="M9 8.5h6M9 11.5h3.5" />
      <path d="M14.6 12.4l1.7 1.7 3-3.4" />
    </Svg>
  );
}

export function IconSettings(p: Props) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.9 19.3a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.7 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.7 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.7h.06A1.7 1.7 0 0 0 10.1 3.14V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.3 9v.06a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15z" />
    </Svg>
  );
}

/** Koło ratunkowe — panel pomocy w zwiniętym menu. */
export function IconLifebuoy(p: Props) {
  return (
    <Svg strokeWidth={1.7} {...p}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3.6" />
      <path d="M5.6 5.6l3.8 3.8M14.6 14.6l3.8 3.8M18.4 5.6l-3.8 3.8M9.4 14.6l-3.8 3.8" />
    </Svg>
  );
}

export function IconChevronDown(p: Props) {
  return (
    <Svg strokeWidth={2} {...p}>
      <path d="M6 9l6 6 6-6" />
    </Svg>
  );
}

export function IconMenu(p: Props) {
  return (
    <Svg strokeWidth={2} {...p}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </Svg>
  );
}

/* --- akcje w wierszach (kolory niosą znaczenie, zob. IconButton) --- */

export function IconEdit(p: Props) {
  return (
    <Svg {...p}>
      <path d="M14.5 5.5l4 4L9 19H5v-4z" />
      <path d="M12.8 7.2l4 4" />
    </Svg>
  );
}

export function IconTrash(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4.5 7h15" />
      <path d="M9.5 7V4.8h5V7" />
      <path d="M6.5 7l1 13h9l1-13" />
      <path d="M10.5 10.5v6.5M13.5 10.5v6.5" />
    </Svg>
  );
}

export function IconLock(p: Props) {
  return (
    <Svg {...p}>
      <rect x="5" y="10.5" width="14" height="9.5" rx="1.6" />
      <path d="M8.4 10.5V8a3.6 3.6 0 0 1 7.2 0v2.5" />
    </Svg>
  );
}

export function IconPlus(p: Props) {
  return (
    <Svg strokeWidth={2} {...p}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  );
}

/** Uchwyt przeciągania (sześć kropek) — kolejność pól nagłówkowych. */
export function IconGrip(p: Props) {
  return (
    <svg viewBox="0 0 24 24" width={p.size ?? 16} height={p.size ?? 16} fill="currentColor" aria-hidden="true" {...p}>
      <circle cx="9" cy="6" r="1.4" />
      <circle cx="15" cy="6" r="1.4" />
      <circle cx="9" cy="12" r="1.4" />
      <circle cx="15" cy="12" r="1.4" />
      <circle cx="9" cy="18" r="1.4" />
      <circle cx="15" cy="18" r="1.4" />
    </svg>
  );
}

export function IconClose(p: Props) {
  return (
    <Svg strokeWidth={2} {...p}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function IconRefresh(p: Props) {
  return (
    <Svg {...p}>
      <path d="M20 11a8 8 0 1 0-.6 4" />
      <path d="M20 5v6h-6" />
    </Svg>
  );
}

/** Dokument — używana m.in. na listach źródeł odpowiedzi. */
export function IconDoc(p: Props) {
  return (
    <Svg {...p}>
      <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z" />
      <path d="M14 3v4h4" />
    </Svg>
  );
}


/** Dokument z „ptaszkiem" — kafelek „Przetworzone" na Dashboardzie. */
export function IconDocCheck(p: Props) {
  return (
    <Svg {...p}>
      <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h6" />
      <path d="M14 3v4h4v4" />
      <path d="M9 11h5M9 15h3" />
      <circle cx="17.5" cy="17.5" r="4.2" />
      <path d="M15.7 17.6l1.4 1.4 2.5-2.8" />
    </Svg>
  );
}

/** Osoba ze znakiem plus — szybka akcja „Dodaj użytkownika". */
export function IconUserPlus(p: Props) {
  return (
    <Svg {...p}>
      <circle cx="10" cy="8" r="3.4" />
      <path d="M3.5 20v-1.5c0-2.5 2.9-4 6.5-4 1 0 1.9.1 2.7.3" />
      <path d="M17.5 14.5v6M14.5 17.5h6" />
    </Svg>
  );
}

/** Folder ze znakiem plus — szybka akcja „Dodaj pliki". */
export function IconFilePlus(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 20V5a1 1 0 0 1 1-1h5l2 2.5h7a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
      <path d="M12 11.5v6M9 14.5h6" />
    </Svg>
  );
}

/** Folder — kafelki w Eksploratorze plików.
 *
 * Zamiast emoji 📁: żółta teczka z Windowsa to glif systemowy, którego macOS
 * i Linux rysują po swojemu, a część dystrybucji wcale. Rysunek własny wygląda
 * tak samo wszędzie.
 */
export function IconFolder(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 20V5a1 1 0 0 1 1-1h5l2 2.5h7a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
    </Svg>
  );
}

/** Dom — początek ścieżki nawigacji (katalog główny). */
export function IconHome(p: Props) {
  return (
    <Svg {...p}>
      <path d="M3.5 10.5L12 3.5l8.5 7" />
      <path d="M5.5 9.8V20h13V9.8" />
      <path d="M10 20v-5.5h4V20" />
    </Svg>
  );
}

/** Strzałka w górę — wysyłanie plików. */
export function IconUpload(p: Props) {
  return (
    <Svg {...p}>
      <path d="M12 19V5.5" />
      <path d="M6.5 11L12 5.5l5.5 5.5" />
    </Svg>
  );
}

/** Strzałka w dół nad kreską — pobieranie pliku. */
export function IconDownload(p: Props) {
  return (
    <Svg {...p}>
      <path d="M12 4.5V17" />
      <path d="M6.5 11.5L12 17l5.5-5.5" />
      <path d="M5 19.5h14" />
    </Svg>
  );
}

/** Oko — podgląd dokumentu. */
export function IconEye(p: Props) {
  return (
    <Svg {...p}>
      <path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="2.8" />
    </Svg>
  );
}

/** Folder ze strzałką — przeniesienie pliku do innego folderu. */
export function IconMove(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 20V5a1 1 0 0 1 1-1h5l2 2.5h7a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
      <path d="M9.5 14h5.5M12.8 11.5L15.5 14l-2.7 2.5" />
    </Svg>
  );
}

/** Widok listy. */
export function IconList(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4 6.5h16M4 12h16M4 17.5h16" />
    </Svg>
  );
}

/** Widok kafelków. */
export function IconGrid(p: Props) {
  return (
    <Svg {...p}>
      <rect x="4" y="4" width="7" height="7" />
      <rect x="13" y="4" width="7" height="7" />
      <rect x="4" y="13" width="7" height="7" />
      <rect x="13" y="13" width="7" height="7" />
    </Svg>
  );
}

/** Papierowy samolot — wysłanie wiadomości w czacie. */
export function IconSend(p: Props) {
  return (
    <Svg {...p}>
      <path d="M4.5 12L20 5l-6.2 14-2.2-5.6z" />
      <path d="M11.6 13.4L20 5" />
    </Svg>
  );
}

/** Strzałka w prawo — przejście do wskazanego dokumentu. */
export function IconChevronRight(p: Props) {
  return (
    <Svg {...p}>
      <path d="M9 5l7 7-7 7" />
    </Svg>
  );
}

/** Iskry — podpowiedzi pytań do bazy wiedzy. */
export function IconSparkle(p: Props) {
  return (
    <Svg {...p}>
      <path d="M12 4.5l1.6 4.2 4.4 1.6-4.4 1.6L12 16.1l-1.6-4.2L6 10.3l4.4-1.6z" />
      <path d="M18 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
    </Svg>
  );
}

/** Kwadrat — przerwanie generowania odpowiedzi. */
export function IconStop(p: Props) {
  return (
    <Svg {...p}>
      <rect x="6.5" y="6.5" width="11" height="11" rx="1.5" />
    </Svg>
  );
}
