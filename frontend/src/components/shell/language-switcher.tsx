'use client';

/** Przełącznik języka interfejsu — na lewo od awatara w górnej belce.
 *
 * Przycisk pokazuje kod ISO 639-1 wielkimi literami (`PL`, `EN`), bo to najkrótsza
 * postać czytelna bez tłumaczenia — nazwa „Polski" po angielsku i „Polish" po polsku
 * znaczą to samo, ale zajmują w belce trzy razy więcej miejsca. Pełne nazwy własne
 * języków są w rozwiniętym menu.
 *
 * Wybrany język znaczymy PTASZKIEM, nie niebieskim tłem: w layoucie 1.5 niebieski
 * jest kolorem akcji, a stan odróżniamy kształtem.
 *
 * Trzy warianty, bo przełącznik stoi w miejscach o różnym kontraście: w białej
 * belce aplikacji, na ciemnym tle ekranu logowania i na białej karcie logowania
 * obok nagłówka. Rozwinięte menu zostaje białe we wszystkich — to ta sama lista
 * i ma wyglądać tak samo.
 */
import { useLocale, useTranslations } from 'next-intl';
import { useEffect, useRef, useState } from 'react';

import { IconCheck, IconGlobe } from '@/components/icons';
import { useEnabledLocales } from '@/components/locale-provider';
import { LOCALE_NAMES, isLocale, type Locale } from '@/i18n/locales';
import { przelaczJezyk } from '@/lib/locale';
import { useAuth } from '@/lib/store';

/** `belka` — biały pasek aplikacji; `ciemny` — tło ekranu logowania;
 *  `naKarcie` — biała karta logowania, w wierszu nagłówka. */
type Wariant = 'belka' | 'ciemny' | 'naKarcie';

const STYL_PRZYCISKU: Record<Wariant, string> = {
  belka: 'text-app-muted hover:bg-app-hover hover:text-app-text',
  ciemny: 'text-slate-300 hover:bg-white/10 hover:text-white',
  // Ten sam kolor co nagłówek „Zaloguj się" tuż obok — kula i kod mają być
  // równie ciemne jak on, a nie przygaszone jak w belce aplikacji.
  naKarcie: 'text-gray-800 hover:bg-gray-100',
};

const STYL_KODU: Record<Wariant, string> = {
  belka: 'text-app-text',
  ciemny: 'text-white',
  naKarcie: 'text-gray-800',
};

export function LanguageSwitcher({ wariant = 'belka' }: { wariant?: Wariant } = {}) {
  const aktywny = useLocale();
  const jezyki = useEnabledLocales();
  const t = useTranslations('shell');
  const { isAuthenticated } = useAuth();
  const [otwarte, setOtwarte] = useState(false);
  const [zmieniany, setZmieniany] = useState<Locale | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!otwarte) return;
    const poza = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOtwarte(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOtwarte(false); };
    document.addEventListener('mousedown', poza);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', poza);
      document.removeEventListener('keydown', esc);
    };
  }, [otwarte]);

  async function wybierz(locale: Locale) {
    setOtwarte(false);
    if (locale === aktywny) return;
    // Przełączenie kończy się przeładowaniem strony, więc stan „w trakcie" nie
    // wróci już do zera — i nie musi. Blokuje podwójne kliknięcie w tym oknie.
    setZmieniany(locale);
    await przelaczJezyk(locale, isAuthenticated);
  }

  const kod = isLocale(aktywny) ? aktywny : jezyki[0];

  // Wdrożenie jednojęzyczne: przełącznik nie ma czego oferować, więc go nie ma.
  if (jezyki.length < 2) return null;

  return (
    // `-mr-2` znosi własny odstęp przycisku, żeby kod języka wypadł w tej samej
    // pionowej linii co prawa krawędź pól formularza pod spodem. Idzie na POJEMNIK,
    // bo rozwinięta lista jest pozycjonowana względem niego (`right-0`).
    <div className={`relative ${wariant === 'naKarcie' ? '-mr-2' : ''}`} ref={menuRef}>
      <button
        onClick={() => setOtwarte((v) => !v)}
        className={`flex items-center gap-1.5 rounded-ctl px-2 py-2 ${STYL_PRZYCISKU[wariant]}`}
        aria-haspopup="menu"
        aria-expanded={otwarte}
        aria-label={t('language')}
        title={t('language')}
        disabled={zmieniany !== null}
      >
        <IconGlobe size={18} />
        <span className={`text-sm font-semibold uppercase ${STYL_KODU[wariant]}`}>{kod}</span>
      </button>

      {otwarte && (
        <div
          role="menu"
          // Lista trzyma tę samą prawą krawędź co kod języka, nie co przycisk:
          // na karcie logowania przycisk wystaje o własny odstęp (`-mr-2` na
          // pojemniku), więc `right-0` wypuściłoby listę poza krawędź pól.
          className={`absolute top-[46px] w-52 rounded-xl border border-app-line bg-white py-1 shadow-card ${
            wariant === 'naKarcie' ? 'right-2' : 'right-0'
          }`}
        >
          <div className="border-b border-app-line px-3 py-2 text-xs text-app-muted">
            {t('language')}
          </div>
          {jezyki.map((locale) => (
            <button
              key={locale}
              onClick={() => wybierz(locale)}
              role="menuitemradio"
              aria-checked={locale === aktywny}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-app-text hover:bg-app-hover"
            >
              <span>
                <span className="font-semibold uppercase">{locale}</span>
                <span className="ml-2 text-app-muted">{LOCALE_NAMES[locale]}</span>
              </span>
              {locale === aktywny && <IconCheck size={16} className="flex-none text-app-text" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
