'use client';

/**
 * Zmiana języka interfejsu po stronie przeglądarki.
 *
 * Wybór trafia w DWA miejsca i każde odpowiada za co innego:
 *
 * - ciasteczko — czyta je układ główny przy renderowaniu na serwerze, więc właściwy
 *   tekst jest w HTML-u od pierwszego renderu i przeżywa wylogowanie (ekran logowania
 *   też ma być w wybranym języku);
 * - `users.locale` — wybór wędruje za kontem na inny komputer.
 *
 * Samo ciasteczko nie wystarczy (znika przy czyszczeniu przeglądarki), sama baza też
 * nie (przed zalogowaniem nie wiadomo, czyj to interfejs).
 */
import { authApi } from '@/lib/api';
import { LOCALE_COOKIE, normalizeLocale, type Locale } from '@/i18n/locales';

/** Rok — wybór języka ma przeżyć zamknięcie przeglądarki, nie tylko sesję. */
const ROK_W_SEKUNDACH = 60 * 60 * 24 * 365;

/** Ślad po ŚWIADOMYM przełączeniu na ekranie logowania — żyje tyle, co karta.
 *
 *  Po co osobny ślad, skoro język siedzi już w ciasteczku: ciasteczko nie mówi,
 *  KTO je ustawił. Na komputerze na oddziale zostaje po poprzedniej zmianie, więc
 *  gdyby samo ciasteczko wygrywało z językiem konta, kolega zalogowany po
 *  Ukraińcu dostawałby ukraiński interfejs. A gdyby zawsze wygrywało konto,
 *  przełącznik na ekranie logowania byłby pozorny — wybór ginąłby po zalogowaniu.
 *  Ślad rozróżnia te dwa przypadki: liczy się wybór zrobiony w TEJ karcie. */
const KLUCZ_WYBORU = 'locale-wybrany-recznie';

export function zapiszCiasteczkoJezyka(locale: Locale): void {
  if (typeof document === 'undefined') return;
  // `SameSite=Lax` wystarcza: ciasteczko czyta wyłącznie własny serwer przy nawigacji.
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${ROK_W_SEKUNDACH}; SameSite=Lax`;
}

export function odczytajCiasteczkoJezyka(): Locale | null {
  if (typeof document === 'undefined') return null;
  const wpis = document.cookie.split('; ').find((c) => c.startsWith(`${LOCALE_COOKIE}=`));
  return normalizeLocale(wpis?.split('=')[1]);
}

export function zapamietajRecznyWybor(locale: Locale): void {
  try {
    sessionStorage.setItem(KLUCZ_WYBORU, locale);
  } catch {
    // Tryb prywatny bywa blokuje zapis. Wtedy wygra język konta — gorzej, ale nie źle.
  }
}

/** Zwraca język wybrany ręcznie w tej karcie i OD RAZU o nim zapomina.
 *  Odczyt jest jednorazowy: ślad ma dotyczyć jednego logowania, nie całej sesji. */
export function odbierzRecznyWybor(): Locale | null {
  try {
    const zapisany = normalizeLocale(sessionStorage.getItem(KLUCZ_WYBORU));
    sessionStorage.removeItem(KLUCZ_WYBORU);
    return zapisany;
  } catch {
    return null;
  }
}

/**
 * Ustawia ciasteczko z języka zapisanego przy koncie — wołane zaraz po zalogowaniu.
 * Konto BEZ wyboru (`locale` puste) nie rusza ciasteczka: osoba mogła przełączyć
 * język na tym komputerze przed zalogowaniem i nie ma powodu jej tego cofać.
 *
 * Zwraca `true`, gdy język SIĘ ZMIENIŁ. Wołający musi wtedy przeładować stronę,
 * a nie przejść do niej po stronie przeglądarki: teksty wchodzą przez układ główny,
 * a ten jest wspólny dla logowania i pulpitu, więc przy nawigacji klienckiej Next
 * go nie przerenderowuje i interfejs zostałby w poprzednim języku.
 */
export function ustawJezykZKonta(locale: string | null | undefined): boolean {
  const kod = normalizeLocale(locale);
  if (!kod || kod === odczytajCiasteczkoJezyka()) return false;
  zapiszCiasteczkoJezyka(kod);
  return true;
}

/**
 * Przełączenie języka: ciasteczko od razu, konto w tle, potem przeładowanie.
 *
 * Przeładowanie, a nie `router.refresh()`: teksty wchodzą przez układ główny, a ten
 * jest przodkiem WSZYSTKICH ekranów — odświeżenie samej trasy zostawiłoby część
 * napisów w poprzednim języku.
 *
 * Nieudany zapis do konta nie może zablokować przełączenia. Interfejs zmienia się
 * mimo to, bo ciasteczko już jest; tracimy tylko przeniesienie wyboru na inny
 * komputer, a nie działanie tutaj.
 */
export async function przelaczJezyk(locale: Locale, zalogowany: boolean): Promise<void> {
  zapiszCiasteczkoJezyka(locale);
  if (!zalogowany) zapamietajRecznyWybor(locale);
  if (zalogowany) {
    try {
      await authApi.updateProfile({ locale });
    } catch {
      // celowo po cichu — zob. komentarz wyżej
    }
  }
  window.location.reload();
}
