'use client';

/**
 * Pomoc — instrukcja obsługi wbudowana w aplikację.
 *
 * Treść NIE jest tu pisana od nowa. Pokazujemy plik wygenerowany przez
 * `docs/instrukcje/generuj.py`, ten sam, który dostaje klient jako HTML i PDF —
 * dzięki temu instrukcja w aplikacji nie może się rozjechać z tą przesłaną
 * mailem. Administrator dostaje wydanie pełne, pozostali wydanie użytkownika,
 * bo opisuje wyłącznie ekrany, które faktycznie widzą.
 */

import { useRef } from 'react';

import { useMarka } from '@/components/marka-provider';
import { useAuth } from '@/lib/store';
import { isAdmin as czyAdmin } from '@/lib/roles';

/** Obraz aplikacji niesie komplet instrukcji dla KAŻDEGO wdrożenia
 *  (`public/pomoc/zco`, `public/pomoc/hirs`), bo różnią się nazwą instancji
 *  i zrzutami ekranu. Katalog wskazuje `marka.pomoc`, czyli zmienna środowiskowa
 *  instancji — nie nazwa z bazy, którą administrator może dziś zmienić. */
const WYDANIA = {
  admin: {
    nazwa: 'Instrukcja administratora',
    plik: 'instrukcja-administratora',
    opis: 'Pełny zakres: dokumenty, uprawnienia, konta i część administracyjna.',
  },
  user: {
    nazwa: 'Instrukcja użytkownika',
    plik: 'instrukcja-uzytkownika',
    opis: 'To, co potrzebne na co dzień: dokumenty, chat i wyszukiwarka.',
  },
} as const;

export default function PomocPage() {
  const { user } = useAuth();
  const marka = useMarka();
  const w = czyAdmin(user) ? WYDANIA.admin : WYDANIA.user;
  const wydanie = {
    ...w,
    html: `/pomoc/${marka.pomoc}/${w.plik}.html`,
    pdf: `/pomoc/${marka.pomoc}/${w.plik}.pdf`,
  };
  const ramka = useRef<HTMLIFrameElement>(null);

  /**
   * Przewinięcie do spisu treści. Instrukcja jest w ramce, więc przewijamy JEJ
   * zawartość, a nie stronę aplikacji — ramka pochodzi z tego samego adresu, więc
   * mamy do niej dostęp. Gdyby kotwicy zabrakło (starszy plik instrukcji),
   * wracamy na sam początek dokumentu.
   */
  const doSpisuTresci = () => {
    try {
      const okno = ramka.current?.contentWindow;
      const spis = okno?.document.getElementById('spis-tresci');
      if (spis) {
        spis.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        okno?.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch {
      /* gdyby instrukcja kiedyś trafiła na inny adres — przycisk po prostu nic nie zrobi */
    }
  };

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 8rem)' }}>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-gray-800">Pomoc</h1>
          <p className="text-sm text-gray-500 mt-1">
            {wydanie.nazwa} — {wydanie.opis}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <a
            href={wydanie.html}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
          >
            Otwórz w nowej karcie
          </a>
          <a
            href={wydanie.pdf}
            download
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
          >
            Pobierz PDF
          </a>
        </div>
      </div>

      {/* Instrukcja jest samodzielnym plikiem HTML (zrzuty ekranu wbudowane
          w treść), więc wystarczy ją osadzić — nie wymaga żadnych zasobów obok. */}
      <iframe
        ref={ramka}
        src={wydanie.html}
        title={wydanie.nazwa}
        className="flex-1 w-full bg-white rounded-lg border border-gray-200 shadow-sm"
      />

      {/* Powrót do spisu treści — przycisk unieruchomiony w rogu EKRANU (nie ramki),
          więc jest pod ręką niezależnie od tego, jak daleko przewinięta jest instrukcja. */}
      <button
        onClick={doSpisuTresci}
        title="Przewiń do spisu treści"
        aria-label="Przewiń do spisu treści"
        className="fixed bottom-6 right-6 z-40 w-12 h-12 rounded-full bg-blue-600 text-white
                   shadow-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500
                   focus:ring-offset-2 transition-colors flex items-center justify-center"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
        </svg>
      </button>
    </div>
  );
}
