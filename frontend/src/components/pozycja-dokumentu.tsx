'use client';

/** Pozycja listy dokumentów — wspólna dla czatu i wyszukiwarki po polach.
 *
 * Oba ekrany pokazują ten sam rodzaj wyniku: zbiór dokumentów wyłoniony z rejestru
 * pól opisowych. W czacie jest to odpowiedź typu LISTA, na ekranie Wyszukiwanie —
 * wynik zapytania po polach; ścieżka po stronie backendu jest dokładnie ta sama
 * (`/api/doc-search`). Skoro dane są te same, prezentacja też ma być ta sama,
 * a jeden komponent gwarantuje to trwale — dwie kopie znaczników rozjechałyby się
 * przy pierwszej korekcie.
 */
import { FileTypeIcon } from '@/components/file-type-icon';
import { IconChevronRight } from '@/components/icons';
import type { DocSearchHit } from '@/lib/api';

export interface DokumentPozycja {
  filename?: string;
  file_id?: number;
  url?: string;
  page?: number;
  doc_type?: string;
  doc_type_name?: string;
  doc_key?: string;
  /** Czy model przywołał ten fragment znacznikiem w treści (dotyczy tylko czatu).
   *  Fragmenty bez znacznika też pokazujemy — bez nich nie da się sprawdzić,
   *  na czym oparta jest odpowiedź. */
  cited?: boolean;
}

/** Pole najlepiej identyfikujące dokument, w kolejności pierwszeństwa. */
export const KEY_FIELDS = ['numer_dokumentu', 'numer', 'numer_aneksu', 'numer_zalacznika', 'data'];

/** Wyniki z rejestru pól → pozycje listy. Jedna konwersja dla obu ekranów. */
export function zHitow(hits: DocSearchHit[], nazwyTypow: Record<string, string>): DokumentPozycja[] {
  return hits.map((h) => {
    const f = h.fields || {};
    const klucz = KEY_FIELDS.map((k) => f[k]).find((v) => !!v);
    return {
      filename: h.filename,
      file_id: h.id,
      doc_type: h.doc_type || undefined,
      doc_type_name: h.doc_type ? nazwyTypow[h.doc_type] || h.doc_type : undefined,
      doc_key: klucz || undefined,
    };
  });
}

/** Etykieta dokumentu: gdy znamy typ, pokazujemy go zamiast samej nazwy pliku
 *  (np. „Zarządzenie 8/2023”), a nazwa pliku ląduje wtedy w drugiej linii. */
export function etykietaDokumentu(d: DokumentPozycja, i: number): string {
  if (d.doc_type_name) return d.doc_key ? `${d.doc_type_name} ${d.doc_key}` : d.doc_type_name;
  return d.filename || d.url || `Dokument ${i + 1}`;
}

interface Props {
  d: DokumentPozycja;
  /** Liczba w plakietce. W czacie odpowiada znacznikowi w treści odpowiedzi,
   *  na ekranie Wyszukiwanie — kolejności na liście. */
  numer: number;
  /** Wyszarzona plakietka dla dokumentów sprawdzonych, ale niewykorzystanych. */
  uzyty?: boolean;
  /** Brak = pozycji nie da się otworzyć (dokument bez identyfikatora). */
  otworz?: () => void;
}

export function PozycjaDokumentu({ d, numer, uzyty = true, otworz }: Props) {
  const etykieta = etykietaDokumentu(d, numer - 1);
  const tresc = (
    <>
      {/* Numer musi odpowiadać znacznikowi w treści odpowiedzi, więc po ukryciu
          części pozycji w numeracji zostają dziury. Dlatego nosi tę samą plakietkę
          co odsyłacz w tekście — czyta się ją jak etykietę odsyłacza, a nie jak
          kolejność na liście. */}
      <span
        className={`grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full text-[11px] font-bold ${
          uzyty ? 'bg-[#eaf1ff] text-[#2455cc]' : 'bg-app-bg text-app-muted'
        }`}
      >
        {numer}
      </span>
      {d.filename && <FileTypeIcon filename={d.filename} size={28} />}
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-app-muted">
          {d.doc_type_name && <span className="font-bold uppercase tracking-[.02em]">{d.doc_type_name}</span>}
          {d.page && <span>str. {d.page}</span>}
        </span>
        <span className="block break-words text-[12px] font-bold text-app-text">{etykieta}</span>
        {d.filename && d.filename !== etykieta && (
          <span className="block break-all text-[11px] text-app-muted">{d.filename}</span>
        )}
      </span>
      {otworz && <span className="shrink-0 text-app-muted"><IconChevronRight size={16} /></span>}
    </>
  );

  const klasy = 'flex w-full items-center gap-2.5 rounded-ctl border border-app-line bg-white px-2.5 py-2 text-left';
  return otworz ? (
    <button onClick={otworz} className={`${klasy} transition-colors hover:bg-app-hover`} title="Otwórz dokument">
      {tresc}
    </button>
  ) : (
    <div className={klasy}>{tresc}</div>
  );
}
