/**
 * Marka instancji — nazwa i kolory czytane z konfiguracji, nie wpisane w kod.
 *
 * Jeden obraz obsługuje wiele wdrożeń: demo uniwersalne (HiRS) i wdrożenia klienckie
 * (np. „ZCO DM") różnią się WYŁĄCZNIE zmiennymi środowiskowymi, więc rozwój dzieje się
 * raz, a każda instancja dostaje tę samą zmianę. Bez tego każda nazwa i każdy kolor
 * oznaczałyby osobną gałąź kodu do utrzymania.
 *
 * Wartości czyta się po stronie serwera (`markaZeSrodowiska`) w układzie głównym i
 * przekazuje w dół przez kontekst — dzięki temu nie ma migotania nazwy po hydratacji
 * ani potrzeby przebudowy obrazu przy zmianie marki. Zmienne NEXT_PUBLIC_* by tu nie
 * zadziałały: są wklejane do kodu w czasie budowy.
 */

export interface Marka {
  /** Nazwa wyświetlana w nagłówku, na logowaniu i w tytule okna */
  nazwa: string;
  /** Zdanie pod nazwą na ekranie logowania */
  opis: string;
  /** Kolor tła paska bocznego */
  tlo: string;
  /** Kolor akcentu (wykresy, wyróżnienia) */
  akcent: string;
  /** Przykład w polu adresu e-mail na logowaniu */
  przykladEmail: string;
  /** Kolor nazwy w nagłówku paska bocznego (HiRS: biały, ZCO: turkus marki) */
  naglowek: string;
  /** Ikona w karcie przeglądarki (ścieżka w `public/`) */
  ikona: string;
  /** Ikona dla ekranu głównego iOS — musi być PNG, SVG tam nie działa */
  ikonaApple: string;
}

/** Domyślnie demo uniwersalne. Wdrożenia klienckie nadpisują to zmiennymi środowiskowymi. */
export const MARKA_DOMYSLNA: Marka = {
  nazwa: 'HiRS',
  opis: 'Hospital Information Retrieval System',
  tlo: '#1d2a4d',
  akcent: '#1fc8ba',
  przykladEmail: 'admin@firma.pl',
  naglowek: '#ffffff',
  ikona: '/ikona-hirs.svg',
  ikonaApple: '/ikona-hirs.png',
};

/**
 * Marka ze zmiennych środowiskowych. WYŁĄCZNIE po stronie serwera — w komponencie
 * klienckim `process.env` nie ma tych wartości (patrz komentarz na górze pliku).
 */
export function markaZeSrodowiska(): Marka {
  const env = process.env;
  return {
    nazwa: env.APP_NAME || MARKA_DOMYSLNA.nazwa,
    opis: env.APP_DESCRIPTION || MARKA_DOMYSLNA.opis,
    tlo: env.BRAND_PRIMARY || MARKA_DOMYSLNA.tlo,
    akcent: env.BRAND_ACCENT || MARKA_DOMYSLNA.akcent,
    przykladEmail: env.LOGIN_EMAIL_PLACEHOLDER || MARKA_DOMYSLNA.przykladEmail,
    naglowek: env.BRAND_HEADER_TEXT || MARKA_DOMYSLNA.naglowek,
    ikona: env.BRAND_ICON || MARKA_DOMYSLNA.ikona,
    ikonaApple: env.BRAND_ICON_APPLE || MARKA_DOMYSLNA.ikonaApple,
  };
}

/**
 * Marka z bazy, z awaryjnym powrotem do zmiennych środowiskowych.
 *
 * Od layoutu 1.5 nazwę, kolor nazwy i ikonę ustawia administrator na ekranie
 * Ustawienia aplikacji — wcześniej trzeba było wpisać je w trzech miejscach przy
 * wdrożeniu i raz się to zemściło (ZCO pokazało ikonę HiRS).
 *
 * Zmienne środowiskowe zostają jako wartość początkowa: świeża instancja wygląda
 * poprawnie, zanim ktokolwiek wejdzie w ustawienia. Awaria backendu nie może
 * zablokować renderowania strony, więc każdy błąd kończy się marką ze środowiska.
 *
 * WYŁĄCZNIE po stronie serwera (używa adresu wewnętrznego `BACKEND_URL`).
 */
export async function markaAktualna(): Promise<Marka> {
  const podstawa = markaZeSrodowiska();
  const adres = process.env.BACKEND_URL;
  if (!adres) return podstawa;
  try {
    const odp = await fetch(`${adres}/api/branding`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(2000),
    });
    if (!odp.ok) return podstawa;
    const d = (await odp.json()) as { nazwa?: string; kolor_nazwy?: string; ikona?: string };
    return {
      ...podstawa,
      nazwa: d.nazwa || podstawa.nazwa,
      naglowek: d.kolor_nazwy || podstawa.naglowek,
      ikona: d.ikona || podstawa.ikona,
      // Ikona dla ekranu głównego iOS zostaje ze środowiska: wymaga PNG-a pod
      // własnym adresem, a wgrana ikona bywa SVG i jest data URI.
    };
  } catch {
    return podstawa;
  }
}

