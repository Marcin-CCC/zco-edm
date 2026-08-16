'use client';

/** Wyszukiwanie po polach metadanych — od layoutu 1.5 osobny ekran.
 *
 * Wcześniej ta sama funkcja mieszkała jako zwijany panel obok czatu. Rozdzielenie
 * jest celowe: czat odpowiada na pytania o TREŚĆ, a ten ekran wyszukuje po
 * strukturze (typ dokumentu, numer, data). Trzymanie obu w jednym oknie wymuszało
 * na użytkowniku decyzję, do którego pola wpisać pytanie — a to jest dokładnie ta
 * decyzja, której nie powinien musieć podejmować.
 *
 * Sam panel zostaje bez zmian: to ten sam komponent, który działał w czacie,
 * razem z „Zapytaj po polsku" i pobieraniem wyników do arkusza.
 */
import { DocSearchPanel } from '@/components/doc-search-panel';

export default function WyszukiwaniePage() {
  return (
    <div>
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-app-text">Wyszukiwanie</h1>
        <p className="mt-1 text-sm text-app-muted">
          Zbuduj zapytanie po polach metadanych i przeszukaj dokumenty.
        </p>
      </div>
      <DocSearchPanel />
    </div>
  );
}
