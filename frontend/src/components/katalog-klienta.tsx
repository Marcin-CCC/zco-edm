'use client';

/** Wkłada katalog napisów tam, skąd sięgną po niego moduły bez kontekstu Reacta
 *  (zob. `src/i18n/klient.ts`). Nic nie renderuje. */
import { useMessages } from 'next-intl';

import { zapamietajKatalog } from '@/i18n/klient';

export function KatalogKlienta() {
  // Podczas renderu, nie w efekcie: komunikat błędu może powstać przy pierwszym
  // żądaniu ze strony, zanim efekty zdążą się wykonać.
  zapamietajKatalog(useMessages() as Parameters<typeof zapamietajKatalog>[0]);
  return null;
}
