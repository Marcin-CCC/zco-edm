'use client';

/**
 * Zestawienie ocen odpowiedzi (administracja).
 *
 * Po co ekran, a nie samo API: oceny negatywne są materiałem na zestaw kontrolny
 * wyszukiwania. Żeby z nich skorzystać, trzeba widzieć naraz pytanie, odpowiedź
 * i to, JAK aplikacja wtedy szukała — bo dopiero ścieżka („zwykła", „terminy",
 * „streszczenia") mówi, gdzie zaczynać dochodzenie.
 */
import { useCallback, useEffect, useState } from 'react';

interface Diagnostyka {
  sciezka?: string;
  terminy?: string[];
  wskazane_streszczeniem?: number[];
  nad_progiem?: number;
  w_kontekscie?: number;
  dobrane?: { filename?: string; page?: number }[];
  scoped_to_files?: boolean;
  search_query?: string | null;
  historia?: boolean;
  wersja?: string;
  zrodla?: { filename?: string; page?: number; score?: number; cited?: boolean }[];
}

interface Ocena {
  id: number;
  ocena: string;
  powod?: string | null;
  pytanie?: string | null;
  odpowiedz?: string | null;
  diagnostyka?: Diagnostyka | null;
  created_at?: string;
}

const IKONA: Record<string, string> = { dobra: '👍', neutralna: '😐', zla: '👎' };
const NAZWA: Record<string, string> = {
  dobra: 'pomogła', neutralna: 'częściowo', zla: 'nie pomogła',
};

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function OcenyPage() {
  const [oceny, setOceny] = useState<Ocena[]>([]);
  const [podsumowanie, setPodsumowanie] = useState<Record<string, number>>({});
  const [tylkoNegatywne, setTylkoNegatywne] = useState(false);
  const [rozwiniete, setRozwiniete] = useState<Record<number, boolean>>({});
  const [blad, setBlad] = useState('');
  const [ladowanie, setLadowanie] = useState(true);

  const wczytaj = useCallback(async () => {
    setLadowanie(true);
    try {
      const res = await fetch(`/api/chat/oceny?tylko_negatywne=${tylkoNegatywne}`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(res.status === 403 ? 'Tylko dla administratora.' : `Błąd ${res.status}`);
      const d = await res.json();
      setOceny(d.oceny || []);
      setPodsumowanie(d.podsumowanie || {});
      setBlad('');
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : 'Nie udało się wczytać ocen.');
    } finally {
      setLadowanie(false);
    }
  }, [tylkoNegatywne]);

  useEffect(() => { wczytaj(); }, [wczytaj]);

  const razem = Object.values(podsumowanie).reduce((a, b) => a + b, 0);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-1">Oceny odpowiedzi</h1>
      <p className="text-sm text-gray-600 mb-4">
        Materiał do poprawiania wyszukiwania. Przy ocenie negatywnej warto zacząć od
        kolumny „ścieżka” — mówi, którym trybem aplikacja szukała dokumentów.
      </p>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        {(['dobra', 'neutralna', 'zla'] as const).map((k) => (
          <span key={k} className="text-sm">
            {IKONA[k]} <strong>{podsumowanie[k] ?? 0}</strong>{' '}
            <span className="text-gray-500">{NAZWA[k]}</span>
          </span>
        ))}
        <span className="text-sm text-gray-500">razem: {razem}</span>
        <label className="text-sm flex items-center gap-2 ml-auto">
          <input
            type="checkbox"
            checked={tylkoNegatywne}
            onChange={(e) => setTylkoNegatywne(e.target.checked)}
          />
          tylko negatywne
        </label>
      </div>

      {blad && <p className="text-red-600 text-sm mb-3">{blad}</p>}
      {ladowanie && <p className="text-gray-500 text-sm">Wczytywanie…</p>}
      {!ladowanie && oceny.length === 0 && !blad && (
        <p className="text-gray-500 text-sm">Nie ma jeszcze żadnych ocen.</p>
      )}

      <div className="space-y-2">
        {oceny.map((o) => {
          const d = o.diagnostyka || {};
          const otwarte = !!rozwiniete[o.id];
          return (
            <div key={o.id} className="border border-gray-200 rounded-md p-3">
              <div className="flex flex-wrap items-baseline gap-2 text-sm">
                <span title={NAZWA[o.ocena]}>{IKONA[o.ocena] || '?'}</span>
                {o.powod && (
                  <span className="rounded-full bg-red-50 text-red-700 px-2 py-0.5 text-xs">
                    {o.powod}
                  </span>
                )}
                <strong className="flex-1">{o.pytanie || '(brak zapisanego pytania)'}</strong>
                <span className="text-xs text-gray-500">
                  {o.created_at ? new Date(o.created_at).toLocaleString('pl-PL') : ''}
                </span>
              </div>

              <div className="mt-1 text-xs text-gray-600 flex flex-wrap gap-3">
                <span>ścieżka: <strong>{d.sciezka || '?'}</strong></span>
                <span>nad progiem: {d.nad_progiem ?? '?'}</span>
                <span>w kontekście: {d.w_kontekscie ?? '?'}</span>
                {!!d.dobrane?.length && <span>dobrane: {d.dobrane.length}</span>}
                {!!d.terminy?.length && <span>zawężenie: {d.terminy.join(', ')}</span>}
                {d.historia && <span>z historią wątku</span>}
                {d.wersja && <span className="text-gray-400">v{d.wersja}</span>}
                <button
                  onClick={() => setRozwiniete((p) => ({ ...p, [o.id]: !otwarte }))}
                  className="text-blue-600 hover:underline ml-auto"
                >
                  {otwarte ? 'Zwiń' : 'Pokaż odpowiedź i źródła'}
                </button>
              </div>

              {otwarte && (
                <div className="mt-2 border-t border-gray-100 pt-2 text-xs">
                  {d.search_query && (
                    <p className="text-gray-500 mb-1">
                      pytanie przepisane do wyszukiwania: <em>{d.search_query}</em>
                    </p>
                  )}
                  <p className="whitespace-pre-wrap text-gray-700">{o.odpowiedz}</p>
                  {!!d.zrodla?.length && (
                    <ul className="mt-2 space-y-0.5">
                      {d.zrodla.map((z, i) => (
                        <li key={i} className={z.cited ? 'text-gray-800' : 'text-gray-400'}>
                          {z.cited ? '📄' : '·'} {z.filename}
                          {z.page ? ` (str. ${z.page})` : ''}
                          {typeof z.score === 'number' ? ` — ${z.score.toFixed(2)}` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
