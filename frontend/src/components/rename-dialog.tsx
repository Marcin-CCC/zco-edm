'use client';

/**
 * Nadawanie nazw z pól dokumentu — podgląd i wykonanie.
 *
 * Operacja dotyka kilkudziesięciu plików naraz i zmienia to, pod czym ludzie znają
 * dokumenty, więc nigdy nie wykonuje się „w ciemno": okno najpierw pokazuje listę
 * stara nazwa → nowa i pozwala każdą pozycję odznaczyć albo poprawić.
 *
 * Nazwy wpisane ręcznie są potrzebne, bo brak pola bierze się częściej ze słabego
 * OCR niż z braku danych w dokumencie — a system nazw ma zostać spójny.
 */
import { useCallback, useEffect, useState } from 'react';

import { filesApi, type RenameProposal } from '@/lib/api';

interface Wiersz extends RenameProposal {
  nazwa: string;      // pole edytowalne
  zaznaczony: boolean;
}

interface Props {
  fileIds: number[];
  /** Etykieta kategorii po slugu — do pokazania, z czego nazwa powstała. */
  etykietaKategorii: (slug: string | null) => string;
  onClose: () => void;
  onDone: (komunikat: string) => void;
}

export function RenameDialog({ fileIds, etykietaKategorii, onClose, onDone }: Props) {
  const [wiersze, setWiersze] = useState<Wiersz[]>([]);
  const [ladowanie, setLadowanie] = useState(true);
  const [zapisywanie, setZapisywanie] = useState(false);
  const [blad, setBlad] = useState('');

  useEffect(() => {
    filesApi
      .renamePreview(fileIds)
      .then((d) =>
        setWiersze(
          (d.pozycje || []).map((p) => ({
            ...p,
            nazwa: p.proponowana || '',
            // Pozycje z problemem są odznaczone: wymagają decyzji człowieka,
            // a nie przeklikania dalej.
            zaznaczony: Boolean(p.proponowana),
          })),
        ),
      )
      .catch((e: unknown) => setBlad(e instanceof Error ? e.message : 'Nie udało się przygotować podglądu'))
      .finally(() => setLadowanie(false));
  }, [fileIds]);

  useEffect(() => {
    const naKlawisz = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', naKlawisz);
    return () => window.removeEventListener('keydown', naKlawisz);
  }, [onClose]);

  const ustaw = useCallback((fileId: number, zmiana: Partial<Wiersz>) => {
    setWiersze((poprzednie) =>
      poprzednie.map((w) => (w.file_id === fileId ? { ...w, ...zmiana } : w)),
    );
  }, []);

  const doZmiany = wiersze.filter((w) => w.zaznaczony && w.nazwa.trim() && w.nazwa !== w.filename);

  async function wykonaj() {
    setZapisywanie(true);
    setBlad('');
    try {
      const wynik = await filesApi.rename(
        doZmiany.map((w) => ({ file_id: w.file_id, filename: w.nazwa.trim() })),
      );
      const pominiete = wynik.pominiete.length
        ? ` Pominięto: ${wynik.pominiete.length}.`
        : '';
      onDone(`Zmieniono nazwę ${wynik.zmienione.length} plikom.${pominiete}`);
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : 'Zmiana nazw nie powiodła się.');
      setZapisywanie(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
      <div className="flex max-h-[85vh] w-full max-w-4xl flex-col rounded-xl bg-white shadow-lg">
        <div className="px-5 pt-5">
          <h2 className="text-lg font-semibold text-gray-800">Nadaj nazwy zgodne z kategorią</h2>
          <p className="mt-1 text-sm text-gray-500">
            Nazwa powstaje ze wzorca przypisanego do kategorii dokumentu. Możesz poprawić
            każdą pozycję albo ją odznaczyć. Dotychczasowa nazwa zostaje zapamiętana.
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {blad && (
            <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {blad}
            </div>
          )}
          {ladowanie ? (
            <div className="py-8 text-center text-gray-500">Przygotowuję podgląd…</div>
          ) : (
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-gray-500">
                  <th className="w-8 py-2"></th>
                  <th className="py-2 pr-3">Obecna nazwa</th>
                  <th className="py-2 pr-3">Kategoria</th>
                  <th className="py-2">Nowa nazwa</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {wiersze.map((w) => (
                  <tr key={w.file_id} className={w.zaznaczony ? '' : 'opacity-60'}>
                    <td className="py-2 align-top">
                      <input
                        type="checkbox"
                        checked={w.zaznaczony}
                        onChange={(e) => ustaw(w.file_id, { zaznaczony: e.target.checked })}
                        className="mt-2"
                      />
                    </td>
                    <td className="py-2 pr-3 align-top text-gray-700 break-all">{w.filename}</td>
                    <td className="py-2 pr-3 align-top text-gray-500 whitespace-nowrap">
                      {etykietaKategorii(w.doc_type)}
                    </td>
                    <td className="py-2 align-top">
                      <input
                        value={w.nazwa}
                        onChange={(e) =>
                          ustaw(w.file_id, { nazwa: e.target.value, zaznaczony: Boolean(e.target.value.trim()) })
                        }
                        placeholder={w.problem || 'wpisz nazwę'}
                        className="w-full rounded-md border border-gray-300 p-1.5 font-mono text-xs text-gray-800"
                      />
                      {w.problem && (
                        <p className="mt-1 text-xs text-amber-700">{w.problem} — wpisz nazwę ręcznie</p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-gray-100 px-5 py-3">
          <span className="text-sm text-gray-500">
            do zmiany: <strong>{doZmiany.length}</strong> z {wiersze.length}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Anuluj
            </button>
            <button
              onClick={wykonaj}
              disabled={zapisywanie || doZmiany.length === 0}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {zapisywanie ? 'Zmieniam…' : `Zmień nazwy (${doZmiany.length})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
