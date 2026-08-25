/**
 * Skąd bierze się język strony przy renderowaniu na serwerze.
 *
 * Kolejność: ciasteczko `locale` → `DEFAULT_LOCALE` wdrożenia → polski. Ciasteczko
 * ustawia przełącznik w górnej belce, a przy logowaniu — wybór zapisany przy koncie
 * (`users.locale`), żeby ta sama osoba dostała swój język także na innym komputerze.
 *
 * Języka PRZEGLĄDARKI świadomie nie pytamy. Na komputerze na oddziale konto bywa
 * wspólne, a przeglądarkę ustawił ktoś inny — interfejs zmieniałby wtedy język
 * między zmianami bez niczyjej decyzji.
 *
 * Katalog innego języka jest DOKŁADANY na polski, nie zastępuje go. Brakujące
 * tłumaczenie daje więc polskie zdanie, a nie klucz `files.uploadButton` — ekran
 * pozostaje używalny, a tłumacz od razu widzi, czego brakuje.
 */
import { cookies } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';

import { BASE_LOCALE, LOCALE_COOKIE, enabledLocales, normalizeLocale, type Locale } from './locales';

type Katalog = { [klucz: string]: string | Katalog };

/** Scalanie w głąb: wartości z `wierzch` wygrywają, brakujące zostają z `spod`. */
function zScalone(spod: Katalog, wierzch: Katalog): Katalog {
  const wynik: Katalog = { ...spod };
  for (const [klucz, wartosc] of Object.entries(wierzch)) {
    const dotychczas = wynik[klucz];
    wynik[klucz] =
      typeof wartosc === 'object' && wartosc !== null && typeof dotychczas === 'object' && dotychczas !== null
        ? zScalone(dotychczas as Katalog, wartosc as Katalog)
        : wartosc;
  }
  return wynik;
}

/** Domyślny język wdrożenia. Błędna wartość w środowisku nie może wywrócić strony. */
export function domyslnyJezyk(): Locale {
  const wlaczone = enabledLocales();
  const zeSrodowiska = normalizeLocale(process.env.DEFAULT_LOCALE);
  return zeSrodowiska && wlaczone.includes(zeSrodowiska) ? zeSrodowiska : BASE_LOCALE;
}

export async function aktualnyJezyk(): Promise<Locale> {
  // Ciasteczko sprawdzamy wobec listy WŁĄCZONYCH, nie tylko istniejących: po
  // wyłączeniu języka na wdrożeniu stare ciasteczko w przeglądarce trzymałoby
  // interfejs w języku, którego administrator już nie chce.
  const zCiasteczka = normalizeLocale(cookies().get(LOCALE_COOKIE)?.value);
  return zCiasteczka && enabledLocales().includes(zCiasteczka) ? zCiasteczka : domyslnyJezyk();
}

export default getRequestConfig(async () => {
  const locale = await aktualnyJezyk();
  const bazowy: Katalog = (await import(`../../messages/${BASE_LOCALE}.json`)).default;
  const messages =
    locale === BASE_LOCALE
      ? bazowy
      : zScalone(bazowy, (await import(`../../messages/${locale}.json`)).default);

  return {
    locale,
    messages,
    // Formaty dat i liczb idą za językiem interfejsu; strefa jest stała, bo cała
    // instalacja stoi w jednej placówce, a daty dokumentów mają być takie same
    // niezależnie od ustawień komputera.
    timeZone: 'Europe/Warsaw',
  };
});
