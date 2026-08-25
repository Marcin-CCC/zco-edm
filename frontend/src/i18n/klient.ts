/**
 * Dostęp do napisów z modułów, które NIE są komponentami.
 *
 * `lib/api.ts` i `lib/eksport-xlsx.ts` zgłaszają błędy sieciowe, a nie mogą sięgnąć
 * po `useTranslations` — nie są komponentami i nie mają kontekstu Reacta. Wcześniej
 * miały te komunikaty wpisane po polsku na sztywno.
 *
 * Katalog wkłada tu raz `KatalogKlienta` renderowany w układzie głównym, wewnątrz
 * dostawcy tłumaczeń. Wystarczy to w praktyce, bo takie błędy powstają w odpowiedzi
 * na działanie użytkownika, czyli długo po pierwszym renderze.
 *
 * Gdy katalogu jeszcze nie ma, wraca sam klucz — nigdy pusty napis. Zdanie
 * „common.sessionExpired" jest brzydkie, ale mówi wprost, co się stało; pusty
 * komunikat błędu nie mówi nic.
 */
type Katalog = { [klucz: string]: string | Katalog };

let katalog: Katalog | null = null;

export function zapamietajKatalog(wiadomosci: Katalog): void {
  katalog = wiadomosci;
}

export function przetlumacz(klucz: string, wartosci?: Record<string, string | number>): string {
  let biezacy: string | Katalog | undefined = katalog ?? undefined;
  for (const czesc of klucz.split('.')) {
    if (typeof biezacy !== 'object' || biezacy === null) return klucz;
    biezacy = biezacy[czesc];
  }
  if (typeof biezacy !== 'string') return klucz;
  if (!wartosci) return biezacy;
  return biezacy.replace(/\{(\w+)\}/g, (calosc, nazwa) =>
    nazwa in wartosci ? String(wartosci[nazwa]) : calosc,
  );
}
