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

import { useAuth } from '@/lib/store';

const WYDANIA = {
  admin: {
    nazwa: 'Instrukcja administratora',
    html: '/pomoc/instrukcja-administratora.html',
    pdf: '/pomoc/instrukcja-administratora.pdf',
    opis: 'Pełny zakres: dokumenty, uprawnienia, konta i część administracyjna.',
  },
  user: {
    nazwa: 'Instrukcja użytkownika',
    html: '/pomoc/instrukcja-uzytkownika.html',
    pdf: '/pomoc/instrukcja-uzytkownika.pdf',
    opis: 'To, co potrzebne na co dzień: dokumenty, baza wiedzy, wyszukiwarka.',
  },
} as const;

export default function PomocPage() {
  const { user } = useAuth();
  const wydanie = user?.role === 'admin' ? WYDANIA.admin : WYDANIA.user;

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
        src={wydanie.html}
        title={wydanie.nazwa}
        className="flex-1 w-full bg-white rounded-lg border border-gray-200 shadow-sm"
      />
    </div>
  );
}
