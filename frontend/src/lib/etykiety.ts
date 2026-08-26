/**
 * Wartości z bazy, które trzeba POKAZAĆ — jedno źródło nazwy i koloru.
 *
 * Statusy przetwarzania i poziomy dostępu do folderów leżą w bazie po angielsku
 * albo po polsku i po nich porównuje kod. Tu trzymamy jedyne mapowanie
 * wartość → klucz napisu, żeby ekrany nie miały każdy swojej kopii.
 *
 * Wartość statusu leży w bazie po polsku i tak też przychodzi z API; po niej
 * porównuje kod (ponów, przerwij, szczegóły błędu), więc sama wartość zostaje.
 * Tłumaczymy wyłącznie to, co widać.
 *
 * Dlaczego osobny plik: mapowanie stało wcześniej WEWNĄTRZ ekranu Kolejka plików.
 * Dashboard pokazywał wtedy surową wartość z bazy, czyli polski napis niezależnie
 * od wybranego języka — i nikt tego nie widział, dopóki ktoś nie porównał dwóch
 * ekranów obok siebie. Kopia mapowania zawsze rozjedzie się z oryginałem; jedno
 * miejsce nie ma jak.
 */
import type { Ton } from '@/components/ui/primitives';

/** Wartość z bazy → klucz napisu w katalogu `queue`. */
export const KLUCZ_STATUSU: Record<string, string> = {
  'W kolejce': 'statusQueued',
  'Przetwarzanie': 'statusProcessing',
  'Przetworzono': 'statusDone',
  'Błąd przetwarzania': 'statusError',
};

/** Wartość z bazy → ton plakietki. Nieznany status dostaje szary, nie czerwony:
 *  nowy status z backendu to nie awaria, tylko coś, czego front jeszcze nie zna. */
export const TON_STATUSU: Record<string, Ton> = {
  'W kolejce': 'gray',
  'Przetwarzanie': 'gray',
  'Przetworzono': 'green',
  'Błąd przetwarzania': 'danger',
};

/**
 * Nazwa statusu w języku interfejsu.
 *
 * `t` to tłumacz katalogu `queue`. Nieznany status pokazujemy DOSŁOWNIE — lepiej
 * surowa wartość z bazy niż pusty znaczek, bo po niej da się dojść, co zaszło.
 */
export function nazwaStatusu(t: (klucz: string) => string, status?: string): string {
  if (!status) return '';
  const klucz = KLUCZ_STATUSU[status];
  return klucz ? t(klucz) : status;
}

export function tonStatusu(status?: string): Ton {
  return (status && TON_STATUSU[status]) || 'gray';
}


/* ----------------------------------------------------- poziomy dostępu */

/** Wartość w bazie → klucz napisu w katalogu `files`. */
export const KLUCZ_POZIOMU: Record<string, string> = {
  read: 'accessRead',
  write: 'accessWrite',
};

/**
 * Nazwa poziomu dostępu w języku interfejsu. `t` to tłumacz katalogu `files`.
 *
 * Mapowanie stało w DWÓCH miejscach — na ekranie Pliki i na Liście dostępów.
 * Pierwsze poprawiłem w 1.6.1 i uznałem sprawę za zamkniętą; drugie zostało po
 * polsku aż do 1.6.3. Dlatego jest tu, a nie w komponencie.
 */
export function nazwaPoziomu(t: (klucz: string) => string, poziom?: string): string {
  if (!poziom) return '';
  const klucz = KLUCZ_POZIOMU[poziom];
  return klucz ? t(klucz) : poziom;
}
