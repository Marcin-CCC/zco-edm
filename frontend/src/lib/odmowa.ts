/**
 * Odmowa modelu („nie ma tego w dokumentach") — rozpoznawanie niezależne od języka.
 *
 * Model zwraca sam znacznik `[[BRAK]]`, a nie zdanie. Powód: cztery mechanizmy
 * zależały od DOSŁOWNEGO brzmienia polskiego zdania — zdejmowanie doklejonego ogona
 * w strumieniu, pomijanie tury w historii, ponowienie pytania „na czysto" i zerowanie
 * źródeł w n8n. Przy odpowiedzi po angielsku model wypisywał własne tłumaczenie
 * i żaden z nich jej nie rozpoznawał: odmowa szła dalej jak zwykła odpowiedź,
 * razem ze źródłami, z których nie skorzystał.
 *
 * Znacznik NIE trafia przed oczy użytkownika — podmieniamy go przy renderowaniu.
 * Do bazy idzie znacznik, więc ta sama rozmowa czytana później w innym języku
 * pokaże odmowę w tym języku.
 *
 * Odpowiednik po stronie serwera: `backend/app/chat/formulka.py`.
 */

/** Znacznik z promptu, po normalizacji do małych liter. */
export const ZNACZNIK_BRAKU = '[[brak]]';

/** Stare polskie zdanie — tak zapisane są rozmowy sprzed zmiany promptu. */
export const ODMOWA_PELNA = 'niestety, nie znaleziono w dokumentach informacji na ten temat.';

/** Obie postacie naraz: kolejność wdrożenia kodu i zmiany promptu nie ma znaczenia. */
export const ODMOWY = [ZNACZNIK_BRAKU, ODMOWA_PELNA];

/** Zdanie pokazywane zamiast znacznika. Po wprowadzeniu tłumaczeń — klucz i18n. */
export const ODMOWA_TEKST = 'Niestety, nie znaleziono w dokumentach informacji na ten temat.';

/** Czy CAŁA treść jest odmową. Wołający podaje tekst już znormalizowany albo surowy. */
export function czyOdmowa(tekst?: string | null): boolean {
  return ODMOWY.includes((tekst || '').replace(/\s+/g, ' ').trim().toLowerCase());
}

/** Treść do pokazania: znacznik zamieniamy na zdanie, resztę zostawiamy bez zmian. */
export function trescDoPokazania(tekst?: string | null): string {
  return czyOdmowa(tekst) ? ODMOWA_TEKST : (tekst || '');
}
