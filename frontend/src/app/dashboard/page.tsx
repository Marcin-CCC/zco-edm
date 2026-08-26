'use client';

import Link from 'next/link';
import { aktywnyJezyk } from '@/i18n/locales';
import { useTranslations } from 'next-intl';
import { useEffect, useState } from 'react';

import { AreaChart, AreaChartPoint } from '@/components/area-chart';
import { QuickActions, StoragePanel, SystemStatusPanel } from '@/components/dashboard/panels';
import { FileTypeIcon, rozmiarPliku } from '@/components/file-type-icon';
import {
  IconDocCheck,
  IconDoc,
  IconFiles,
  IconUsers,
} from '@/components/icons';
import { Badge, Card, EmptyState, PageHeader, Sub, inputClass } from '@/components/ui/primitives';
import { dashboardApi, type SystemStatus } from '@/lib/api';
import { kiedy } from '@/lib/czas';
import { isAdmin as czyAdmin } from '@/lib/roles';
import { nazwaStatusu, tonStatusu } from '@/lib/etykiety';
import { useAuth } from '@/lib/store';

// Kolory serii sprawdzone pod kątem rozróżnialności także przy zaburzeniach
// widzenia barw (jedna seria na wykres, więc bez legendy — nazywa ją tytuł karty).
// Świadomie NIE bierzemy tu koloru marki: jest edytowalny w Ustawieniach, więc
// administrator mógłby ustawić niebieski i oba wykresy stałyby się nierozróżnialne.
const KOLOR_PARSOWANIE = '#2563eb';
const KOLOR_ZAPYTANIA = '#10b8b3';

const OKRESY = [7, 30, 90];

/** Inicjały do awatara. Dwa znaki: z imienia i nazwiska, a z jednego słowa — pierwsza litera. */
function inicjaly(nazwa: string): string {
  const czlony = nazwa.trim().split(/\s+/).filter(Boolean);
  if (!czlony.length) return '?';
  if (czlony.length === 1) return czlony[0].slice(0, 1).toUpperCase();
  return (czlony[0][0] + czlony[czlony.length - 1][0]).toUpperCase();
}

/** Polska odmiana rzeczownika po liczbie: 1 plik, 2 pliki, 5 plików. */
// UWAGA: ta funkcja znała wyłącznie polskie reguły. Zostaje wyłącznie dlatego,
// że nie ma już wołających — liczebniki idą przez komunikaty ICU.
function odmiana(n: number, jeden: string, dwa: string, piec: string): string {
  const ost = n % 10;
  const dwie = n % 100;
  if (n === 1) return jeden;
  if (ost >= 2 && ost <= 4 && (dwie < 10 || dwie >= 20)) return dwa;
  return piec;
}

type Kafelek = {
  label: string;
  value: string;
  suffix?: string;
  href?: string;
  trend?: number | null;
  jednostka?: string;
  Icon: React.ComponentType<{ size?: number }>;
  ton: 'blue' | 'teal' | 'purple' | 'orange';
};

const TONY: Record<Kafelek['ton'], { tlo: string; kolor: string }> = {
  blue: { tlo: '#edf4ff', kolor: 'var(--app-blue)' },
  teal: { tlo: '#e2f8f6', kolor: 'var(--app-teal)' },
  purple: { tlo: '#f0edff', kolor: 'var(--app-purple)' },
  orange: { tlo: '#fff0e7', kolor: 'var(--app-orange)' },
};

export default function DashboardPage() {
  const { user } = useAuth();
  const isAdmin = czyAdmin(user);

  // Jeden wybór okresu dla całego ekranu. Makieta ma trzy przełączniki (nagłówek
  // + każdy wykres osobno); świadomie robimy jeden, bo trzy niezależne zakresy na
  // jednym ekranie rodzą pytanie „dlaczego wykres pokazuje co innego niż kafelek".
  const [dni, setDni] = useState(30);
  const [stats, setStats] = useState<any>({ users: null, documents: 0, folders: 0, processed: 0 });
  const [ostatnie, setOstatnie] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<AreaChartPoint[]>([]);
  const [queries, setQueries] = useState<AreaChartPoint[]>([]);
  const [scope, setScope] = useState<'all' | 'own'>('own');
  const [chartsLoading, setChartsLoading] = useState(true);
  // Rozbicie na użytkowników: endpoint odpowiada tylko administratorowi (403 dla reszty),
  // więc pusta lista = panel nie jest w ogóle rysowany.
  const [wgUzytkownikow, setWgUzytkownikow] = useState<
    { user_id: number; name: string; parsed: number; queries: number }[]
  >([]);
  const [stan, setStan] = useState<SystemStatus | null>(null);
  const [bladStanu, setBladStanu] = useState(false);

  useEffect(() => {
    dashboardApi.recentFiles(5)
      .then(setOstatnie)
      .catch(() => { /* lista podręczna — brak nie psuje reszty ekranu */ });
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    dashboardApi.systemStatus()
      .then(setStan)
      .catch(() => setBladStanu(true));
  }, [isAdmin]);

  useEffect(() => {
    setChartsLoading(true);
    dashboardApi.activity(dni)
      .then((d) => {
        setParsed(d.days.map((day, i) => ({ day, value: d.parsed[i] ?? 0 })));
        setQueries(d.days.map((day, i) => ({ day, value: d.queries[i] ?? 0 })));
        setScope(d.scope);
      })
      .catch(() => { /* wykresy nie są krytyczne dla reszty dashboardu */ })
      .finally(() => setChartsLoading(false));

    dashboardApi.byUser(dni)
      .then((d) => setWgUzytkownikow(d?.users || []))
      .catch(() => { /* 403 dla nie-admina — panel po prostu się nie pokazuje */ });
  }, [dni]);

  useEffect(() => {
    dashboardApi.stats(dni)
      .then(setStats)
      .catch((err: any) => setError(err.message || t('errStats')))
      .finally(() => setLoading(false));
  }, [dni]);

  const t = useTranslations('dashboard');
  const tWspolne = useTranslations('common');
  const tPliki = useTranslations('files');
  // Nazwy statusow mieszkaja w katalogu `queue` — to ten sam zestaw, co w Kolejce plikow.
  const tKolejka = useTranslations('queue');
  const etykietyDat = { dzis: tWspolne('today'), wczoraj: tWspolne('yesterday') };

  const suma = (p: AreaChartPoint[]) => p.reduce((a, b) => a + b.value, 0);

  // Wykresy mają różny zakres dla zwykłego użytkownika: pliki widzi te, do których
  // ma dostęp, a zapytania wyłącznie własne — stąd dwa osobne opisy.
  const opisPlikow = scope === 'all' ? t('scopeAll') : t('scopeMine');
  const opisZapytan = scope === 'all' ? t('scopeAll') : t('scopeMyQueries');

  // Kafelek bez `href` jest tylko liczbą — nie udaje odnośnika. Kolejka plików
  // leży w Administracji, więc „Przetworzone" prowadzi tam wyłącznie administratora.
  const kafelki: Kafelek[] = [
    ...(stats.users !== null && stats.users !== undefined
      ? [{
          label: t('tileUsers'), value: String(stats.users), href: '/dashboard/users',
          trend: stats.trend_users, Icon: IconUsers, ton: 'blue' as const,
        }]
      : []),
    {
      label: t('tileFolders'), value: String(stats.folders ?? 0), href: '/dashboard/files',
      trend: stats.trend_folders, Icon: IconFiles, ton: 'teal',
    },
    {
      label: t('tileDocuments'), value: String(stats.documents ?? 0), href: '/dashboard/files',
      trend: stats.trend_documents, Icon: IconDoc, ton: 'purple',
    },
    {
      label: t('tileProcessed'),
      value: `${(stats.processed_percent ?? 0).toLocaleString(aktywnyJezyk(), { maximumFractionDigits: 1 })}%`,
      suffix: `${stats.processed ?? 0} z ${stats.documents ?? 0}`,
      href: isAdmin ? '/dashboard/file-queue' : undefined,
      trend: stats.trend_processed,
      jednostka: ' pkt proc.',
      Icon: IconDocCheck,
      ton: 'orange',
    },
  ];

  // Panel aktywności pokazuje tylko tych, którzy coś zrobili w wybranym okresie.
  // Konta bez aktywności są w danych (backend zwraca wszystkie), ale lista
  // kilkunastu zer nie jest informacją — liczbę takich kont podajemy pod spodem.
  const aktywni = wgUzytkownikow.filter((u) => u.parsed + u.queries > 0);
  const bezczynni = wgUzytkownikow.length - aktywni.length;

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <select
            value={dni}
            onChange={(e) => setDni(Number(e.target.value))}
            className={`${inputClass} w-auto`}
            aria-label={t('rangeLabel')}
          >
            {OKRESY.map((d) => (
              <option key={d} value={d}>{t('rangeOption', { days: d })}</option>
            ))}
          </select>
        }
      />

      {error && (
        <div className="mb-4 rounded-ctl border border-[#fecdd3] bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {error}
        </div>
      )}

      {/* Kafelki. Trend pokazujemy tylko wtedy, gdy backend go policzył — przy zbyt
          małej podstawie zwraca `null`, bo procent liczony od jedynki nie jest
          informacją (zob. MIN_PODSTAWA_TRENDU w dashboard/router.py).

          Dlatego kafelki wyrównujemy do GÓRY, a nie do środka: bez trendu kafelek
          jest niższy od sąsiadów, a siatka rozciąga wszystkie do wysokości
          najwyższego. Przy wyśrodkowaniu ikona i podpis takiego kafelka zjeżdżały
          w dół i rząd wyglądał na rozstrojony. */}
      <div className={`mb-[18px] grid grid-cols-1 gap-[18px] md:grid-cols-2 ${kafelki.length === 4 ? 'xl:grid-cols-4' : 'xl:grid-cols-3'}`}>
        {kafelki.map((k) => {
          const ton = TONY[k.ton];
          const tresc = (
            <>
              <span
                className="grid h-[46px] w-[46px] shrink-0 place-items-center rounded-[13px]"
                style={{ background: ton.tlo, color: ton.kolor }}
              >
                <k.Icon size={23} />
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] text-[#5e6f89]">{k.label}</span>
                <span className="mt-[3px] block text-[26px] font-extrabold leading-none text-app-text">
                  {loading ? '…' : k.value}
                  {!loading && k.suffix && (
                    <span className="ml-2 text-xs font-medium text-app-muted">{k.suffix}</span>
                  )}
                </span>
                {!loading && typeof k.trend === 'number' && (
                  <span className={`mt-2 block text-[11px] font-semibold ${k.trend >= 0 ? 'text-app-green' : 'text-app-danger'}`}>
                    {k.trend >= 0 ? '↑' : '↓'} {Math.abs(k.trend).toLocaleString(aktywnyJezyk(), { maximumFractionDigits: 1 })}
                    {k.jednostka || '%'}{' '}
                    <span className="font-normal text-app-muted">{t('vsPrevious', { days: dni })}</span>
                  </span>
                )}
              </span>
            </>
          );
          return k.href ? (
            <Link
              key={k.label}
              href={k.href}
              className="flex items-start gap-3.5 rounded-card border border-app-line bg-white p-[18px] shadow-card transition-colors hover:bg-app-hover"
            >
              {tresc}
            </Link>
          ) : (
            <Card key={k.label} className="flex items-start gap-3.5 p-[18px]">{tresc}</Card>
          );
        })}
      </div>

      {/* Wykresy aktywności */}
      <div className="mb-[18px] grid grid-cols-1 gap-[18px] lg:grid-cols-2">
        <Card className="p-4">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-bold text-app-text">{t('parsingStats')}</h2>
              <p className="mt-0.5 text-[22px] font-extrabold text-app-text">
                {chartsLoading ? '…' : suma(parsed).toLocaleString(aktywnyJezyk())}{' '}
                <span className="text-[12px] font-normal text-app-muted">
                  {t('parsedCount', { count: suma(parsed) })}
                </span>
              </p>
            </div>
            <span className="whitespace-nowrap pt-1 text-[11px] text-app-muted">{t('rangeDays', { days: dni })} · {opisPlikow}</span>
          </div>
          {chartsLoading ? (
            <div className="flex h-[179px] items-center justify-center text-sm text-app-muted">{tWspolne('loading')}</div>
          ) : (
            <AreaChart
              data={parsed}
              color={KOLOR_PARSOWANIE}
              unitLabel={t('chartParsedUnit')}
              emptyText={t('chartParsedEmpty', { days: dni })}
            />
          )}
        </Card>

        <Card className="p-4">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-bold text-app-text">{t('queryStats')}</h2>
              <p className="mt-0.5 text-[22px] font-extrabold text-app-text">
                {chartsLoading ? '…' : suma(queries).toLocaleString(aktywnyJezyk())}{' '}
                <span className="text-[12px] font-normal text-app-muted">
                  {t('queriesCount', { count: suma(queries) })}
                </span>
              </p>
            </div>
            <span className="whitespace-nowrap pt-1 text-[11px] text-app-muted">{t('rangeDays', { days: dni })} · {opisZapytan}</span>
          </div>
          {chartsLoading ? (
            <div className="flex h-[179px] items-center justify-center text-sm text-app-muted">{tWspolne('loading')}</div>
          ) : (
            <AreaChart
              data={queries}
              color={KOLOR_ZAPYTANIA}
              unitLabel={t('chartQueriesUnit')}
              emptyText={t('chartQueriesEmpty', { days: dni })}
            />
          )}
        </Card>
      </div>

      <div className="mb-[18px] grid grid-cols-1 gap-[18px] lg:grid-cols-2">
        {/* Ostatnio dodane dokumenty — rzut oka, nie zamiennik listy plików.
            Widoczność wg uprawnień: backend zwraca tylko dostępne foldery. */}
        <Card className="p-4">
          <div className="mb-2 flex items-start justify-between">
            <h2 className="text-[16px] font-bold text-app-text">{t('recentDocuments')}</h2>
            <Link href="/dashboard/files" className="text-[11px] font-bold text-app-blue hover:underline">
              {t('seeAll')}
            </Link>
          </div>
          {ostatnie.length === 0 ? (
            <EmptyState title={t('noDocuments')} hint={t('noDocumentsHint')} />
          ) : (
            <ul className="-mx-1">
              {ostatnie.map((f) => (
                <li
                  key={f.id}
                  className="flex items-center gap-3 rounded-ctl border-b border-app-line px-1 py-3 last:border-b-0 hover:bg-app-hover"
                >
                  <FileTypeIcon filename={f.filename} />
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-[13px] font-bold text-app-text">{f.filename}</span>
                    <Sub>{f.folder || tPliki('rootFolderInline')}</Sub>
                  </span>
                  <span className="hidden whitespace-nowrap text-[12px] text-app-muted sm:block">
                    {rozmiarPliku(f.size)}
                  </span>
                  <Badge tone={tonStatusu(f.status)}>
                    {nazwaStatusu(tKolejka, f.status)}
                  </Badge>
                  <span className="w-[92px] shrink-0 text-right text-[11px] text-app-muted">{kiedy(f.created_at, etykietyDat)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Aktywność użytkowników. Makieta pokazuje tu dziennik zdarzeń („przeglądał
            dokument…"); my pokazujemy zestawienie z danych, które system NAPRAWDĘ
            zbiera. Rejestrowanie odczytów to osobna decyzja — bez niej byłaby to
            atrapa udająca dziennik. Panel widzi wyłącznie administrator (403). */}
        {wgUzytkownikow.length > 0 && (
          <Card className="p-4">
            <div className="mb-2 flex items-start justify-between">
              <div>
                <h2 className="text-[16px] font-bold text-app-text">{t('userActivity')}</h2>
                {/* Okres podajemy RAZ, w nagłówku. Powtórzony przy każdym wierszu
                    byłby tą samą informacją pięć razy pod rząd. */}
                <p className="mt-0.5 text-[11px] text-app-muted">{t('lastDays', { days: dni })}</p>
              </div>
              <Link href="/dashboard/users" className="text-[11px] font-bold text-app-blue hover:underline">
                {t('seeAllUsers')}
              </Link>
            </div>
            {aktywni.length === 0 ? (
              <EmptyState
                title={t('noActivity')}
                hint={t('noActivityHint', { days: dni })}
              />
            ) : (
              <>
                <ul className="-mx-1">
                  {aktywni.slice(0, 6).map((u) => (
                    <li
                      key={u.user_id}
                      className="flex items-center gap-3 border-b border-app-line px-1 py-3 last:border-b-0"
                    >
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#edf4ff] text-[12px] font-extrabold text-app-blue">
                        {inicjaly(u.name)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-bold text-app-text">{u.name}</span>
                        <Sub>
                          {u.parsed > 0 && t('filesCount', { count: u.parsed })}
                          {u.parsed > 0 && u.queries > 0 && ' · '}
                          {u.queries > 0 && t('questionsCount', { count: u.queries })}
                        </Sub>
                      </span>
                    </li>
                  ))}
                </ul>
                {(aktywni.length > 6 || bezczynni > 0) && (
                  <p className="mt-2.5 text-[11px] text-app-muted">
                    {aktywni.length > 6 && t('shownOf', { total: aktywni.length })}
                    {bezczynni > 0 && t('idleAccounts', { count: bezczynni })}
                  </p>
                )}
              </>
            )}
          </Card>
        )}
      </div>

      {/* Dolny rząd. Bez uprawnień administratora zostają same Szybkie akcje —
          panele stanu serwera są administracyjne (zob. panels.tsx). */}
      <div className={`mb-[18px] grid grid-cols-1 gap-[18px] ${isAdmin ? 'lg:grid-cols-[1.3fr_0.9fr_0.95fr]' : ''}`}>
        <QuickActions isAdmin={isAdmin} />
        {isAdmin && <StoragePanel stan={stan} />}
        {isAdmin && <SystemStatusPanel stan={stan} blad={bladStanu} />}
      </div>

      <div className="rounded-card border border-[#cddffb] bg-[#eef4ff] p-5 text-center">
        <p className="text-sm text-[#2455cc]">
          {t('safeNote')}
        </p>
      </div>
    </div>
  );
}
