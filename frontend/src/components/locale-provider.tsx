'use client';

/**
 * Udostępnia komponentom klienckim listę języków włączonych na tym wdrożeniu.
 *
 * Ta sama droga co przy marce: wartość czyta układ główny (komponent serwerowy,
 * bo `UI_LANGUAGES` jest zmienną środowiskową) i podaje w dół przez kontekst.
 * Zmienne NEXT_PUBLIC_* by tu nie zadziałały — są wklejane do kodu przy budowie,
 * a jeden obraz obsługuje oba wdrożenia.
 */
import { createContext, useContext } from 'react';

import { BASE_LOCALE, type Locale } from '@/i18n/locales';

const KontekstJezykow = createContext<Locale[]>([BASE_LOCALE]);

export function LocaleProvider({ locales, children }: { locales: Locale[]; children: React.ReactNode }) {
  return <KontekstJezykow.Provider value={locales}>{children}</KontekstJezykow.Provider>;
}

/** Języki do wyboru. Jeden element = nie ma czego przełączać. */
export function useEnabledLocales(): Locale[] {
  return useContext(KontekstJezykow);
}
