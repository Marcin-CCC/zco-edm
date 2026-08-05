'use client';

/**
 * Udostępnia markę komponentom klienckim. Wartości wchodzą raz, z układu głównego
 * (komponent serwerowy czytający zmienne środowiskowe), więc nazwa jest w HTML-u już
 * przy pierwszym renderze — bez migotania po hydratacji.
 */
import { createContext, useContext } from 'react';

import { MARKA_DOMYSLNA, type Marka } from '@/lib/marka';

const KontekstMarki = createContext<Marka>(MARKA_DOMYSLNA);

export function MarkaProvider({ marka, children }: { marka: Marka; children: React.ReactNode }) {
  return <KontekstMarki.Provider value={marka}>{children}</KontekstMarki.Provider>;
}

export function useMarka(): Marka {
  return useContext(KontekstMarki);
}
