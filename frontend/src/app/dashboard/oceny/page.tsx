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
import { czasLokalny } from '@/lib/czas';

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
  zrodla?: Zrodlo[];
}

interface Ocena {
  id: number;
  ocena: string;
  powod?: string | null;
  pytanie?: string | null;
  odpowiedz?: string | null;
  diagnostyka?: Diagnostyka | null;
  uzytkownik?: string | null;
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

interface Zrodlo {
  filename?: string | null;
  page?: number | null;
  file_id?: number | null;
  cited?: boolean | null;
  score?: number | null;
}

interface Pytanie {
  message_id: number;
  pytanie?: string | null;
  odpowiedz?: string | null;
  zrodla?: Zrodlo[];
  uzytkownik?: string | null;
  user_id?: number | null;
  rola?: string | null;
  created_at?: string;
  ocena?: string | null;
  powod?: string | null;
  diagnostyka?: Diagnostyka | null;
}

interface Pytajacy {
  id: number;
  nazwa: string;
  rola?: string | null;
}

/** Otwarcie dokumentu w nowej karcie — tak samo jak lista źródeł w Bazie wiedzy. */
async function otworzDokument(fileId: number) {
  try {
    const res = await fetch(`/api/files/${fileId}/download`, { headers: authHeaders() });
    if (!res.ok) throw new Error(`Błąd pobierania (${res.status})`);
    window.open(URL.createObjectURL(await res.blob()), '_blank');
  } catch (e: unknown) {
    alert(e instanceof Error ? e.message : 'Nie udało się otworzyć dokumentu.');
  }
}

/**
 * Lista źródeł — JEDEN komponent dla obu zakładek.
 *
 * Powód wydzielenia: źródła przychodzą tu dwiema drogami (z `messages.sources`
 * w rejestrze i z migawki planu w ocenach) i przy pierwszym podejściu poprawiłem
 * odnośniki tylko w jednej. Wspólny komponent sprawia, że nie da się poprawić
 * jednego miejsca, zapominając o drugim.
 *
 * Wyszarzone pozycje to fragmenty, które model dostał, ale się na nie nie powołał —
 * ta sama konwencja co pod odpowiedzią w Bazie wiedzy.
 */
function ListaZrodel({ zrodla, dobrane = [], uklad = 'pion' }: {
  zrodla?: Zrodlo[];
  /** Fragmenty doklejone przez dobór z dokumentu-zwycięzcy (zob. app/chat/dobor.py) */
  dobrane?: { filename?: string; page?: number }[];
  uklad?: 'pion' | 'poziom';
}) {
  if (!zrodla?.length) return null;

  // Fragment dobrany NIE MA trafności — nie przeszedł progu, tylko został wskazany
  // celowo. W n8n dostaje wartość równą progowi, a na ścieżkach z wyłączonym progiem
  // jest to zero, więc wyświetlał się jako „0.00" i czytało się to jak „zerowa
  // trafność". To nieprawda, więc zamiast liczby pokazujemy etykietę.
  const czyDobrany = (z: Zrodlo) => dobrane.some(
    (d) => d.filename === z.filename && (d.page ?? null) === (z.page ?? null),
  );

  return (
    <ul className={uklad === 'pion'
      ? 'mt-2 space-y-0.5 text-xs'
      : 'mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs'}>
      {zrodla.map((z, i) => {
        const dobrany = czyDobrany(z);
        const nieuzyte = z.cited === false;
        const nazwa = `${z.filename ?? '(bez nazwy)'}${z.page ? ` (str. ${z.page})` : ''}`;
        return (
          <li key={i}>
            {z.file_id ? (
              <button
                onClick={() => otworzDokument(z.file_id!)}
                title="Otwórz dokument"
                className={`text-left hover:underline ${nieuzyte ? 'text-gray-400' : 'text-blue-600'}`}
              >
                📄 {nazwa}
              </button>
            ) : (
              <span className={nieuzyte ? 'text-gray-400' : 'text-gray-600'}>📄 {nazwa}</span>
            )}
            {dobrany ? (
              <span
                className="ml-1 rounded bg-amber-50 text-amber-700 px-1 py-0.5 text-[10px]"
                title="Fragment doklejony celowo z rozpoznanego dokumentu — próg trafności go nie dotyczy"
              >
                dobrany
              </span>
            ) : (
              typeof z.score === 'number' && z.score > 0 && (
                <span className="ml-1 text-gray-400">— {z.score.toFixed(2)}</span>
              )
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Objaśnienie kolorów i etykiet — raz na ekran, nie przy każdym wierszu. */
function Legenda() {
  return (
    <p className="text-xs text-gray-500 mb-3 flex flex-wrap gap-x-4 gap-y-1">
      <span><span className="text-blue-600">📄 niebieski</span> — model powołał się na ten fragment znacznikiem [Źródło N]</span>
      <span><span className="text-gray-400">📄 szary</span> — fragment był w kontekście, ale model go nie oznaczył (mógł z niego skorzystać bez znacznika)</span>
      <span><span className="rounded bg-amber-50 text-amber-700 px-1">dobrany</span> — doklejony celowo z rozpoznanego dokumentu, poza progiem trafności</span>
    </p>
  );
}

const ROLE_PL: Record<string, string> = {
  admin: 'administrator', doctor: 'lekarz', medical_staff: 'personel medyczny',
  technician: 'technik', office_staff: 'administracja', guest: 'gość',
};

export default function OcenyPage() {
  const [widok, setWidok] = useState<'oceny' | 'rejestr'>('oceny');
  const [oceny, setOceny] = useState<Ocena[]>([]);
  const [podsumowanie, setPodsumowanie] = useState<Record<string, number>>({});
  const [pytania, setPytania] = useState<Pytanie[]>([]);
  const [wgRoli, setWgRoli] = useState<Record<string, number>>({});
  const [tylkoNegatywne, setTylkoNegatywne] = useState(false);
  const [tylkoOcenione, setTylkoOcenione] = useState(false);
  const [pytajacy, setPytajacy] = useState<Pytajacy[]>([]);
  const [ktoryUzytkownik, setKtoryUzytkownik] = useState<string>('');   // '' = wszyscy
  const [rozwiniete, setRozwiniete] = useState<Record<number, boolean>>({});
  const [blad, setBlad] = useState('');
  const [ladowanie, setLadowanie] = useState(true);

  useEffect(() => {
    fetch('/api/chat/uzytkownicy-pytajacy', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setPytajacy(d.uzytkownicy || []))
      .catch(() => { /* brak listy = filtr po prostu się nie pokaże */ });
  }, []);

  const wczytaj = useCallback(async () => {
    setLadowanie(true);
    try {
      const osoba = ktoryUzytkownik ? `&user_id=${ktoryUzytkownik}` : '';
      const url = widok === 'oceny'
        ? `/api/chat/oceny?tylko_negatywne=${tylkoNegatywne}${osoba}`
        : `/api/chat/rejestr?tylko_ocenione=${tylkoOcenione}${osoba}`;
      const res = await fetch(url, { headers: authHeaders() });
      if (!res.ok) throw new Error(res.status === 403 ? 'Tylko dla administratora.' : `Błąd ${res.status}`);
      const d = await res.json();
      if (widok === 'oceny') {
        setOceny(d.oceny || []);
        setPodsumowanie(d.podsumowanie || {});
      } else {
        setPytania(d.pytania || []);
        setWgRoli(d.wg_roli || {});
      }
      setBlad('');
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : 'Nie udało się wczytać danych.');
    } finally {
      setLadowanie(false);
    }
  }, [widok, tylkoNegatywne, tylkoOcenione, ktoryUzytkownik]);

  useEffect(() => { wczytaj(); }, [wczytaj]);

  const razem = Object.values(podsumowanie).reduce((a, b) => a + b, 0);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-1">Lista odpowiedzi</h1>
      <p className="text-sm text-gray-600 mb-4">
        {widok === 'oceny'
          ? 'Materiał do poprawiania wyszukiwania. Przy ocenie negatywnej warto zacząć od pola „ścieżka” — mówi, którym trybem aplikacja szukała dokumentów.'
          : 'Wszystkie zadane pytania, także te bez oceny. W fazie testów pokazuje, o co ludzie faktycznie pytają i kto z systemu korzysta.'}
      </p>

      <div className="flex gap-1 mb-4 border-b border-gray-200">
        {([['oceny', 'Oceny'], ['rejestr', 'Wszystkie pytania']] as const).map(([k, etykieta]) => (
          <button
            key={k}
            onClick={() => setWidok(k)}
            className={`px-3 py-1.5 text-sm -mb-px border-b-2 ${
              widok === k
                ? 'border-blue-600 text-blue-700 font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {etykieta}
          </button>
        ))}
      </div>

      {/* Filtr osoby dotyczy OBU zakładek — administrator śledzi jedną osobę
          niezależnie od tego, czy patrzy na oceny, czy na cały ruch. */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <label className="text-sm text-gray-600">Użytkownik:</label>
        <select
          value={ktoryUzytkownik}
          onChange={(e) => setKtoryUzytkownik(e.target.value)}
          className="border border-gray-300 rounded-md px-2 py-1 text-sm"
        >
          <option value="">wszyscy</option>
          {pytajacy.map((u) => (
            <option key={u.id} value={u.id}>
              {u.nazwa}{u.rola ? ` — ${ROLE_PL[u.rola] || u.rola}` : ''}
            </option>
          ))}
        </select>
        {ktoryUzytkownik && (
          <button
            onClick={() => setKtoryUzytkownik('')}
            className="text-sm text-blue-600 hover:underline"
          >
            wyczyść
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        {widok === 'oceny' ? (
          <>
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
          </>
        ) : (
          <>
            {Object.entries(wgRoli).map(([rola, ile]) => (
              <span key={rola} className="text-sm text-gray-600">
                {ROLE_PL[rola] || rola}: <strong>{ile}</strong>
              </span>
            ))}
            <label className="text-sm flex items-center gap-2 ml-auto">
              <input
                type="checkbox"
                checked={tylkoOcenione}
                onChange={(e) => setTylkoOcenione(e.target.checked)}
              />
              pokaż tylko ocenione
            </label>
          </>
        )}
      </div>

      <Legenda />

      {blad && <p className="text-red-600 text-sm mb-3">{blad}</p>}
      {ladowanie && <p className="text-gray-500 text-sm">Wczytywanie…</p>}
      {!ladowanie && !blad && widok === 'oceny' && oceny.length === 0 && (
        <p className="text-gray-500 text-sm">Nie ma jeszcze żadnych ocen.</p>
      )}
      {!ladowanie && !blad && widok === 'rejestr' && pytania.length === 0 && (
        <p className="text-gray-500 text-sm">
          {tylkoOcenione ? 'Żadne z pytań nie zostało jeszcze ocenione.' : 'Nie zadano jeszcze żadnych pytań.'}
        </p>
      )}

      {widok === 'rejestr' && (
        <div className="space-y-2">
          {pytania.map((p) => {
            const otwarte = !!rozwiniete[p.message_id];
            const d = p.diagnostyka || {};
            return (
              <div key={p.message_id} className="border border-gray-200 rounded-md p-3">
                <div className="flex flex-wrap items-baseline gap-2 text-sm">
                  {p.ocena ? <span title={NAZWA[p.ocena]}>{IKONA[p.ocena]}</span>
                           : <span className="text-gray-300" title="bez oceny">·</span>}
                  {p.powod && (
                    <span className="rounded-full bg-red-50 text-red-700 px-2 py-0.5 text-xs">
                      {p.powod}
                    </span>
                  )}
                  <strong className="flex-1">{p.pytanie || '(brak pytania w historii)'}</strong>
                  <span className="text-xs text-gray-500">
                    {p.uzytkownik} · {ROLE_PL[p.rola || ''] || p.rola}
                  </span>
                  <span className="text-xs text-gray-400">
                    {czasLokalny(p.created_at)}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-600 flex flex-wrap gap-3">
                  {d.sciezka && <span>ścieżka: <strong>{d.sciezka}</strong></span>}
                  <button
                    onClick={() => setRozwiniete((s) => ({ ...s, [p.message_id]: !otwarte }))}
                    className="text-blue-600 hover:underline ml-auto"
                  >
                    {otwarte ? 'Zwiń' : 'Pokaż odpowiedź'}
                  </button>
                </div>

                <ListaZrodel zrodla={p.zrodla} dobrane={d.dobrane} uklad="poziom" />

                {otwarte && (
                  <p className="mt-2 border-t border-gray-100 pt-2 text-xs whitespace-pre-wrap text-gray-700">
                    {p.odpowiedz}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className={widok === 'oceny' ? 'space-y-2' : 'hidden'}>
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
                {o.uzytkownik && <span className="text-xs text-gray-500">{o.uzytkownik}</span>}
                <span className="text-xs text-gray-400">{czasLokalny(o.created_at)}</span>
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
                  <ListaZrodel zrodla={d.zrodla} dobrane={d.dobrane} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
