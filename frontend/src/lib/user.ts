/** Pomocnicze funkcje wokół danych zalogowanego użytkownika. */

/**
 * Inicjały do awatara — z imienia i nazwiska, a gdy go brak, z nazwy użytkownika.
 * „Marcin Kowalski" → MK, „marcin" → MA, brak danych → „?".
 */
export function inicjaly(fullName?: string | null, username?: string | null): string {
  const zrodlo = (fullName || '').trim() || (username || '').trim();
  if (!zrodlo) return '?';
  const czesci = zrodlo.split(/\s+/).filter(Boolean);
  const litery = czesci.length > 1 ? czesci[0][0] + czesci[1][0] : zrodlo.slice(0, 2);
  return litery.toUpperCase();
}

// Etykiety ról NIE są już tutaj — słownik ról trzyma baza, a front czyta go
// przez `useRoles()` z `@/lib/roles`. Lista w kodzie byłaby nieaktualna w chwili,
// gdy administrator założy własną rolę.
