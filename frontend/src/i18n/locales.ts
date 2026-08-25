/**
 * Języki interfejsu — lista i reguły wspólne dla całego frontu.
 *
 * Polski jest BAZOWY: w nim powstają teksty i on jest zapasem, gdy w innym języku
 * brakuje tłumaczenia (scalanie katalogów robi `request.ts`). Dzięki temu ekran,
 * do którego jeszcze nie doszliśmy, pokazuje polskie zdanie, a nie klucz w rodzaju
 * `files.uploadButton` — użytkownik widzi wtedy coś zrozumiałego, a tłumacz od razu
 * wie, czego brakuje.
 *
 * Odpowiednik po stronie serwera: `backend/app/locales.py`.
 */

/** Kod bazowy. Nie jest „jednym z" — dla pozostałych jest wartością zapasową. */
export const BASE_LOCALE = 'pl';

/** Kolejność ta sama, co przycisków w przełączniku. Kody ISO 639-1.
 *  Bazowy pierwszy, potem angielski (nim pokazujemy system), dalej alfabetycznie. */
export const LOCALES = ['pl', 'en', 'cs', 'de', 'es', 'uk'] as const;

export type Locale = (typeof LOCALES)[number];

/** Podpis w przełączniku i w `<html lang>`. Nazwa własna języka, nie tłumaczona. */
export const LOCALE_NAMES: Record<Locale, string> = {
  pl: 'Polski',
  en: 'English',
  cs: 'Čeština',
  de: 'Deutsch',
  es: 'Español',
  uk: 'Українська',
};

/** Nazwa ciasteczka, z którego układ główny czyta język przy renderowaniu na serwerze. */
export const LOCALE_COOKIE = 'locale';

/**
 * Języki WŁĄCZONE na tym wdrożeniu (`UI_LANGUAGES`, np. `pl,en`).
 *
 * Po co osobna lista obok `LOCALES`: katalog tłumaczeń może istnieć, zanim będzie
 * kompletny. Wdrożenie klienckie ma wtedy zostać jednojęzyczne — przy jednej pozycji
 * przełącznik znika sam, bo nie ma między czym wybierać.
 *
 * Język bazowy jest zawsze w środku: to on jest zapasem dla wszystkich pozostałych.
 * WYŁĄCZNIE po stronie serwera — `process.env` w przeglądarce tych wartości nie ma.
 */
export function enabledLocales(): Locale[] {
  const zSrodowiska = (process.env.UI_LANGUAGES || '')
    .split(',')
    .map((k) => normalizeLocale(k))
    .filter((k): k is Locale => k !== null);
  const lista = zSrodowiska.length ? zSrodowiska : [...LOCALES];
  // Kolejność zawsze z `LOCALES`, żeby przyciski nie skakały przy zmianie zmiennej.
  return LOCALES.filter((k) => k === BASE_LOCALE || lista.includes(k));
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/**
 * Kod sprowadzony do postaci z listy albo `null`.
 *
 * Przyjmujemy zapisy przychodzące z przeglądarek i nagłówków — `EN`, `en-US`,
 * `en_GB` — bo ciasteczko bywa ustawiane też ręcznie. Wartości spoza listy
 * odrzucamy: nie ma dla nich katalogu tłumaczeń.
 */
export function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) return null;
  const kod = value.trim().replace('_', '-').split('-')[0].toLowerCase();
  return isLocale(kod) ? kod : null;
}
