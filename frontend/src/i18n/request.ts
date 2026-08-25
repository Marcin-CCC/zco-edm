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

/**
 * Poprawki tłumaczeń z bazy — warstwa NA katalogu z obrazu.
 *
 * Ta sama droga co marka (`lib/marka.ts`): odczyt po stronie serwera, krótki limit
 * czasu i awaryjny powrót do samego katalogu. Awaria backendu nie może zostawić
 * użytkownika bez napisów — najwyżej bez cudzych poprawek.
 *
 * Bez pamięci podręcznej, jak przy marce: to wywołanie WEWNĄTRZ sieci dockerowej,
 * a poprawka wpisana przez tłumacza ma być widoczna od razu po odświeżeniu strony.
 */
async function poprawkiZBazy(locale: Locale): Promise<Record<string, string>> {
  const adres = process.env.BACKEND_URL;
  if (!adres || locale === BASE_LOCALE) return {};
  try {
    const odp = await fetch(`${adres}/api/translations/${locale}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(2000),
    });
    if (!odp.ok) return {};
    const dane = await odp.json();
    return dane && typeof dane === 'object' ? dane : {};
  } catch {
    return {};
  }
}

/** Nakłada klucze z kropkami („shell.logout") na zagnieżdżony katalog. */
function zPoprawkami(katalog: Katalog, poprawki: Record<string, string>): Katalog {
  if (!Object.keys(poprawki).length) return katalog;
  const wynik: Katalog = JSON.parse(JSON.stringify(katalog));
  for (const [klucz, wartosc] of Object.entries(poprawki)) {
    if (typeof wartosc !== 'string') continue;
    const czesci = klucz.split('.');
    let biezacy = wynik;
    let poprawny = true;
    for (const czesc of czesci.slice(0, -1)) {
      const nastepny = biezacy[czesc];
      // Poprawka do klucza, którego w katalogu nie ma (np. po usunięciu ekranu),
      // jest po prostu pomijana — nie zakładamy pod nią nowych gałęzi.
      if (typeof nastepny !== 'object' || nastepny === null) { poprawny = false; break; }
      biezacy = nastepny as Katalog;
    }
    if (poprawny) biezacy[czesci[czesci.length - 1]] = wartosc;
  }
  return wynik;
}

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
  let messages: Katalog = bazowy;
  if (locale !== BASE_LOCALE) {
    // Trzy warstwy, każda nadpisuje poprzednią: polski (zapas) → katalog języka
    // z obrazu → poprawki wpisane przez tłumacza w zakładce Języki.
    const zObrazu = zScalone(bazowy, (await import(`../../messages/${locale}.json`)).default);
    messages = zPoprawkami(zObrazu, await poprawkiZBazy(locale));
  }

  return {
    locale,
    messages,
    // Formaty dat i liczb idą za językiem interfejsu; strefa jest stała, bo cała
    // instalacja stoi w jednej placówce, a daty dokumentów mają być takie same
    // niezależnie od ustawień komputera.
    timeZone: 'Europe/Warsaw',
  };
});
