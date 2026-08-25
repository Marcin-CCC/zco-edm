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
 */
import { useLocale, useTranslations } from 'next-intl';
import { useEffect, useRef, useState } from 'react';

import { IconCheck, IconGlobe } from '@/components/icons';
import { useEnabledLocales } from '@/components/locale-provider';
import { LOCALE_NAMES, isLocale, type Locale } from '@/i18n/locales';
import { przelaczJezyk } from '@/lib/locale';
import { useAuth } from '@/lib/store';

export function LanguageSwitcher() {
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
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOtwarte((v) => !v)}
        className="flex items-center gap-1.5 rounded-ctl px-2 py-2 text-app-muted hover:bg-app-hover hover:text-app-text"
        aria-haspopup="menu"
        aria-expanded={otwarte}
        aria-label={t('language')}
        title={t('language')}
        disabled={zmieniany !== null}
      >
        <IconGlobe size={18} />
        <span className="text-sm font-semibold uppercase text-app-text">{kod}</span>
      </button>

      {otwarte && (
        <div
          role="menu"
          className="absolute right-0 top-[46px] w-44 rounded-xl border border-app-line bg-white py-1 shadow-card"
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
