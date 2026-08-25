/**
 * Czas z API → czas lokalny użytkownika.
 *
 * Backend zapisuje znaczniki czasu przez `datetime.utcnow()`, czyli UTC BEZ informacji
 * o strefie, i tak też je serializuje: „2026-08-09T09:12:00". Przeglądarka traktuje
 * taki napis jako czas LOKALNY, więc latem w Polsce pokazywała godzinę wcześniejszą
 * o dwie — pytanie zadane przed chwilą wyglądało na sprzed dwóch godzin.
 *
 * Dokładanie „Z" mówi przeglądarce, że to UTC, a ona przelicza na strefę użytkownika.
 * Napis, który strefę już niesie (z „Z" albo z przesunięciem), zostawiamy w spokoju —
 * dzięki temu funkcja zadziała też, gdy API zacznie kiedyś zwracać czas ze strefą.
 *
 * Ta sama poprawka żyła wcześniej lokalnie w Kolejce plików; tutaj jest raz, dla
 * wszystkich ekranów.
 */

import { aktywnyJezyk } from '@/i18n/locales';

/** Data z napisu ISO; napis bez strefy rozumiemy jako UTC. */
export function parsujUtc(iso: string): Date {
  const maStrefe = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(maStrefe ? iso : iso + 'Z');
}

/** Data i godzina w strefie użytkownika, np. „09.08.2026, 11:12". */
export function czasLokalny(
  iso?: string | null,
  opcje: Intl.DateTimeFormatOptions = { dateStyle: 'short', timeStyle: 'short' },
): string {
  if (!iso) return '—';
  const d = parsujUtc(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(aktywnyJezyk(), opcje);
}

/** Sama data w strefie użytkownika. */
export function dataLokalna(
  iso?: string | null,
  opcje: Intl.DateTimeFormatOptions = { dateStyle: 'short' },
): string {
  if (!iso) return '—';
  const d = parsujUtc(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString(aktywnyJezyk(), opcje);
}

/** Sama data kalendarzowa („2026-08-21" → „21.08.2026"), BEZ przeliczania stref.
 *
 * Osobna funkcja, bo `dataLokalna` dokłada „Z" i przelicza na strefę użytkownika —
 * przy dacie bez godziny potrafi to cofnąć ją o jeden dzień. Data ważności treści
 * jest zapisem kalendarzowym („stan na 21 sierpnia"), a nie momentem w czasie.
 */
export function dataKalendarzowa(wartosc?: string | null): string {
  if (!wartosc) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(wartosc);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : wartosc;
}

/** Sama godzina w strefie użytkownika. */
export function godzinaLokalna(
  iso?: string | null,
  opcje: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' },
): string {
  if (!iso) return '—';
  const d = parsujUtc(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString(aktywnyJezyk(), opcje);
}

/** Znacznik czasu w formie z makiety 1.5: „Dzisiaj, 11:32", „Wczoraj, 16:07",
 *  a starsze — „14.08, 09:18".
 *
 * Rok pomijamy przy datach z bieżącego roku: na liście „ostatnio dodanych"
 * czterocyfrowy rok przy każdej pozycji to szum, a nie informacja.
 */
export function kiedy(
  iso?: string | null,
  /** „Dzisiaj"/„Wczoraj" w języku interfejsu. Ten moduł nie jest komponentem, więc
   *  nie sięgnie po tłumaczenia sam — wołający podaje je z `useTranslations`.
   *  Wartości domyślne są polskie, żeby wywołanie bez etykiet nadal działało. */
  etykiety: { dzis: string; wczoraj: string } = { dzis: 'Dzisiaj', wczoraj: 'Wczoraj' },
): string {
  if (!iso) return '—';
  const d = parsujUtc(iso);
  if (isNaN(d.getTime())) return '—';

  const godzina = d.toLocaleTimeString(aktywnyJezyk(), { hour: '2-digit', minute: '2-digit' });
  const dzien = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dzis = new Date();
  const dzisDzien = new Date(dzis.getFullYear(), dzis.getMonth(), dzis.getDate());
  const roznica = Math.round((dzisDzien.getTime() - dzien.getTime()) / 86_400_000);

  if (roznica === 0) return `${etykiety.dzis}, ${godzina}`;
  if (roznica === 1) return `${etykiety.wczoraj}, ${godzina}`;
  const data = d.toLocaleDateString(aktywnyJezyk(),
    d.getFullYear() === dzis.getFullYear()
      ? { day: '2-digit', month: '2-digit' }
      : { day: '2-digit', month: '2-digit', year: 'numeric' });
  return `${data}, ${godzina}`;
}
