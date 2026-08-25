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
import { aktywnyJezyk } from '@/i18n/locales';
import { useTranslations } from 'next-intl';
import { IconDoc } from '@/components/icons';
import { czasLokalny } from '@/lib/czas';
import { Card, EmptyState, PageHeader, inputClass } from '@/components/ui/primitives';
import { roleLabel, useRoles } from '@/lib/roles';
import { trescDoPokazania } from '@/lib/odmowa';

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
// KLUCZE, nie napisy: to stała modułu, a napis idzie za językiem interfejsu.
const NAZWA_KLUCZ: Record<string, string> = {
  dobra: 'rateGood', neutralna: 'ratePartial', zla: 'rateBad',
};

function authHeaders(): Record<string, string> {
  // `X-UI-Language`: backend podaje klucz komunikatu i tłumaczy go dopiero przy
  // odpowiedzi, więc musi wiedzieć, co widzi osoba po drugiej stronie. Nagłówek
  // idzie z KAŻDYM żądaniem, także tym bez tokenu.
  const token = localStorage.getItem('auth_token');
  const naglowki: Record<string, string> = { 'X-UI-Language': aktywnyJezyk() };
  if (token) naglowki.Authorization = `Bearer ${token}`;
  return naglowki;
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
async function otworzDokument(fileId: number, komunikatBledu: string, bladPobierania: string) {
  try {
    const res = await fetch(`/api/files/${fileId}/download`, { headers: authHeaders() });
    if (!res.ok) throw new Error(bladPobierania.replace('{status}', String(res.status)));
    window.open(URL.createObjectURL(await res.blob()), '_blank');
  } catch (e: unknown) {
    alert(e instanceof Error ? e.message : komunikatBledu);
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
  const t = useTranslations('answers');
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
                onClick={() => otworzDokument(z.file_id!, t('errOpenDocument'), t('errFetch', { status: '{status}' }))}
                title={t('openDocument')}
                className={`inline-flex items-center gap-1 text-left hover:underline ${nieuzyte ? 'text-app-muted' : 'text-app-blue'}`}
              >
                <IconDoc size={13} /> {nazwa}
              </button>
            ) : (
              <span className={`inline-flex items-center gap-1 ${nieuzyte ? 'text-app-muted' : 'text-app-text'}`}><IconDoc size={13} /> {nazwa}</span>
            )}
            {dobrany ? (
              <span
                className="ml-1 rounded bg-amber-50 text-amber-700 px-1 py-0.5 text-[10px]"
                title={t('pickedTitle')}
              >
                {t('pickedBadge')}
              </span>
            ) : (
              typeof z.score === 'number' && z.score > 0 && (
                <span className="ml-1 text-app-muted">— {z.score.toFixed(2)}</span>
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
  const t = useTranslations('answers');
  return (
    <p className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-app-muted">
      <span><span className="text-app-blue">{t('legendBlue')}</span>{t('legendBlueText')}</span>
      <span><span className="text-app-muted">{t('legendGrey')}</span>{t('legendGreyText')}</span>
      <span><span className="rounded bg-amber-50 text-amber-700 px-1">{t('pickedBadge')}</span>{t('legendPickedText')}</span>
    </p>
  );
}


/** Pasek nawigacji po stronach. Ten sam układ co pod listą plików. */
function Stronicowanie({ strona, naStronie, razem, ustawStrone, ustawNaStronie }: {
  strona: number;
  naStronie: number;
  razem: number;
  ustawStrone: (n: number) => void;
  ustawNaStronie: (n: number) => void;
}) {
  const t = useTranslations('answers');
  if (!razem) return null;
  const stron = Math.max(1, Math.ceil(razem / naStronie));
  const od = (strona - 1) * naStronie + 1;
  const doPozycji = Math.min(strona * naStronie, razem);
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-card border border-app-line bg-white px-[18px] py-3 text-[12px] text-app-muted">
      <span>{razem <= naStronie ? t('rangeAll', { total: razem, total2: razem }) : t('rangeOf', { from: od, to: doPozycji, total: razem })}</span>
      {stron > 1 && (
        <span className="flex items-center gap-1.5">
          <button
            disabled={strona === 1}
            onClick={() => ustawStrone(strona - 1)}
            className="rounded-ctl border border-app-line px-2 py-1 disabled:opacity-40"
          >‹</button>
          <span className="px-1">{t('pageOf', { page: strona, total: stron })}</span>
          <button
            disabled={strona >= stron}
            onClick={() => ustawStrone(strona + 1)}
            className="rounded-ctl border border-app-line px-2 py-1 disabled:opacity-40"
          >›</button>
        </span>
      )}
      <label className="flex items-center gap-2">
        {t('perPage')}
        <select
          value={naStronie}
          onChange={(e) => { ustawNaStronie(Number(e.target.value)); ustawStrone(1); }}
          className={`${inputClass} h-8 w-auto py-0`}
        >
          {[25, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
    </div>
  );
}


export default function OcenyPage() {
  const t = useTranslations('answers');
  const { roles } = useRoles();
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
  // Stronicowanie. Filtry zawężają CAŁOŚĆ po stronie bazy, a tu wybieramy tylko,
  // który jej kawałek pobrać — `razemPozycji` mówi, ile jest po filtrach.
  const [strona, setStrona] = useState(1);
  const [naStronie, setNaStronie] = useState(50);
  const [razemPozycji, setRazemPozycji] = useState(0);

  /** Zmiana filtra musi wracać na pierwszą stronę — inaczej po zawężeniu listy
   *  zostaje się na stronie, której już nie ma, i widać pustkę. */
  const zmienFiltr = (ustaw: () => void) => { ustaw(); setStrona(1); };

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
      const zakres = `&limit=${naStronie}&offset=${(strona - 1) * naStronie}`;
      const url = widok === 'oceny'
        ? `/api/chat/oceny?tylko_negatywne=${tylkoNegatywne}${osoba}${zakres}`
        : `/api/chat/rejestr?tylko_ocenione=${tylkoOcenione}${osoba}${zakres}`;
      const res = await fetch(url, { headers: authHeaders() });
      if (!res.ok) throw new Error(res.status === 403 ? 'Tylko dla administratora.' : t('errStatus', { status: res.status }));
      const d = await res.json();
      if (widok === 'oceny') {
        setOceny(d.oceny || []);
        setPodsumowanie(d.podsumowanie || {});
      } else {
        setPytania(d.pytania || []);
        setWgRoli(d.wg_roli || {});
      }
      setRazemPozycji(d.razem ?? 0);
      setBlad('');
    } catch (e: unknown) {
      setBlad(e instanceof Error ? e.message : t('errLoad'));
    } finally {
      setLadowanie(false);
    }
  }, [widok, tylkoNegatywne, tylkoOcenione, ktoryUzytkownik, strona, naStronie]);

  useEffect(() => { wczytaj(); }, [wczytaj]);

  const razem = Object.values(podsumowanie).reduce((a, b) => a + b, 0);

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={
          widok === 'oceny'
            ? t('descRatings')
            : t('descAll')
        }
      />

      {/* Wybrana zakładka na szarym tle z białym elementem aktywnym — niebieskie
          wypełnienie jest w tym layoucie zarezerwowane dla akcji. */}
      <div className="mb-4 inline-flex gap-1 rounded-ctl bg-[#eef1f6] p-1">
        {([['oceny', 'Oceny'], ['rejestr', 'Wszystkie pytania']] as const).map(([k, etykieta]) => (
          <button
            key={k}
            onClick={() => zmienFiltr(() => setWidok(k))}
            aria-pressed={widok === k}
            className={`rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors ${
              widok === k ? 'bg-white text-app-text shadow-sm' : 'text-app-muted hover:text-app-text'
            }`}
          >
            {etykieta}
          </button>
        ))}
      </div>

      {/* Filtr osoby dotyczy OBU zakładek — administrator śledzi jedną osobę
          niezależnie od tego, czy patrzy na oceny, czy na cały ruch. */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <label className="text-[13px] text-app-muted">{t('user')}</label>
        <select
          value={ktoryUzytkownik}
          onChange={(e) => zmienFiltr(() => setKtoryUzytkownik(e.target.value))}
          className={`${inputClass} h-9 w-auto`}
        >
          <option value="">{t('everyone')}</option>
          {pytajacy.map((u) => (
            <option key={u.id} value={u.id}>
              {u.nazwa}{u.rola ? ` — ${roleLabel(roles, u.rola).toLowerCase()}` : ''}
            </option>
          ))}
        </select>
        {ktoryUzytkownik && (
          <button
            onClick={() => zmienFiltr(() => setKtoryUzytkownik(''))}
            className="text-[13px] font-semibold text-app-blue hover:underline"
          >
            {t('clear')}
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        {widok === 'oceny' ? (
          <>
            {(['dobra', 'neutralna', 'zla'] as const).map((k) => (
              <span key={k} className="text-sm">
                {IKONA[k]} <strong>{podsumowanie[k] ?? 0}</strong>{' '}
                <span className="text-app-muted">{t(NAZWA_KLUCZ[k])}</span>
              </span>
            ))}
            <span className="text-[13px] text-app-muted">razem: {razem}</span>
            <label className="text-sm flex items-center gap-2 ml-auto">
              <input
                type="checkbox"
                checked={tylkoNegatywne}
                onChange={(e) => zmienFiltr(() => setTylkoNegatywne(e.target.checked))}
              />
              {t('onlyNegative')}
            </label>
          </>
        ) : (
          <>
            {Object.entries(wgRoli).map(([rola, ile]) => (
              <span key={rola} className="text-[13px] text-app-muted">
                {roleLabel(roles, rola).toLowerCase()}: <strong>{ile}</strong>
              </span>
            ))}
            <label className="text-sm flex items-center gap-2 ml-auto">
              <input
                type="checkbox"
                checked={tylkoOcenione}
                onChange={(e) => zmienFiltr(() => setTylkoOcenione(e.target.checked))}
              />
              {t('onlyRated')}
            </label>
          </>
        )}
      </div>

      <Legenda />

      {blad && <p className="mb-3 text-sm text-app-danger">{blad}</p>}
      {ladowanie && <Card><EmptyState title={t('loading')} /></Card>}
      {!ladowanie && !blad && widok === 'oceny' && oceny.length === 0 && (
        <Card><EmptyState title={t('emptyRatings')} hint={t('emptyRatingsHint')} /></Card>
      )}
      {!ladowanie && !blad && widok === 'rejestr' && pytania.length === 0 && (
        <Card>
          <EmptyState
            title={tylkoOcenione ? t('emptyNoneRated') : t('emptyNoQuestions')}
          />
        </Card>
      )}

      {widok === 'rejestr' && (
        <div className="space-y-2">
          {pytania.map((p) => {
            const otwarte = !!rozwiniete[p.message_id];
            const d = p.diagnostyka || {};
            return (
              <div key={p.message_id} className="rounded-card border border-app-line bg-white p-3.5 shadow-card">
                <div className="flex flex-wrap items-baseline gap-2 text-sm">
                  {p.ocena ? <span title={t(NAZWA_KLUCZ[p.ocena])}>{IKONA[p.ocena]}</span>
                           : <span className="text-app-line" title={t('noRating')}>·</span>}
                  {p.powod && (
                    <span className="rounded-full bg-app-dangerbg px-2 py-0.5 text-[11px] font-bold text-app-danger">
                      {p.powod}
                    </span>
                  )}
                  <strong className="flex-1">{p.pytanie || '(brak pytania w historii)'}</strong>
                  <span className="text-[11px] text-app-muted">
                    {p.uzytkownik} · {roleLabel(roles, p.rola).toLowerCase()}
                  </span>
                  <span className="text-[11px] text-app-muted">
                    {czasLokalny(p.created_at)}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-app-muted">
                  {d.sciezka && <span>{t('path')} <strong>{d.sciezka}</strong></span>}
                  <button
                    onClick={() => setRozwiniete((s) => ({ ...s, [p.message_id]: !otwarte }))}
                    className="ml-auto font-semibold text-app-blue hover:underline"
                  >
                    {otwarte ? t('collapse') : t('showAnswer')}
                  </button>
                </div>

                <ListaZrodel zrodla={p.zrodla} dobrane={d.dobrane} uklad="poziom" />

                {otwarte && (
                  <p className="mt-2 whitespace-pre-wrap border-t border-app-line pt-2 text-xs text-app-text">
                    {trescDoPokazania(p.odpowiedz)}
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
            <div key={o.id} className="rounded-card border border-app-line bg-white p-3.5 shadow-card">
              <div className="flex flex-wrap items-baseline gap-2 text-sm">
                <span title={t(NAZWA_KLUCZ[o.ocena])}>{IKONA[o.ocena] || '?'}</span>
                {o.powod && (
                  <span className="rounded-full bg-app-dangerbg px-2 py-0.5 text-[11px] font-bold text-app-danger">
                    {o.powod}
                  </span>
                )}
                <strong className="flex-1">{o.pytanie || t('noQuestionSaved')}</strong>
                {o.uzytkownik && <span className="text-[11px] text-app-muted">{o.uzytkownik}</span>}
                <span className="text-[11px] text-app-muted">{czasLokalny(o.created_at)}</span>
              </div>

              <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-app-muted">
                <span>{t('path')} <strong>{d.sciezka || '?'}</strong></span>
                <span>nad progiem: {d.nad_progiem ?? '?'}</span>
                <span>w kontekście: {d.w_kontekscie ?? '?'}</span>
                {!!d.dobrane?.length && <span>dobrane: {d.dobrane.length}</span>}
                {!!d.terminy?.length && <span>zawężenie: {d.terminy.join(', ')}</span>}
                {d.historia && <span>{t('withThread')}</span>}
                {d.wersja && <span className="text-app-muted">v{d.wersja}</span>}
                <button
                  onClick={() => setRozwiniete((p) => ({ ...p, [o.id]: !otwarte }))}
                  className="text-blue-600 hover:underline ml-auto"
                >
                  {otwarte ? t('collapse') : t('showAnswerAndSources')}
                </button>
              </div>

              {otwarte && (
                <div className="mt-2 border-t border-app-line pt-2 text-xs">
                  {d.search_query && (
                    <p className="mb-1 text-app-muted">
                      {t('rewritten')} <em>{d.search_query}</em>
                    </p>
                  )}
                  <p className="whitespace-pre-wrap text-app-text">{trescDoPokazania(o.odpowiedz)}</p>
                  <ListaZrodel zrodla={d.zrodla} dobrane={d.dobrane} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Stronicowanie
        strona={strona}
        naStronie={naStronie}
        razem={razemPozycji}
        ustawStrone={setStrona}
        ustawNaStronie={setNaStronie}
      />
    </div>
  );
}
