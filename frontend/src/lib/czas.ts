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
  return isNaN(d.getTime()) ? '—' : d.toLocaleString('pl-PL', opcje);
}

/** Sama data w strefie użytkownika. */
export function dataLokalna(
  iso?: string | null,
  opcje: Intl.DateTimeFormatOptions = { dateStyle: 'short' },
): string {
  if (!iso) return '—';
  const d = parsujUtc(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('pl-PL', opcje);
}

/** Sama godzina w strefie użytkownika. */
export function godzinaLokalna(
  iso?: string | null,
  opcje: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' },
): string {
  if (!iso) return '—';
  const d = parsujUtc(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('pl-PL', opcje);
}
