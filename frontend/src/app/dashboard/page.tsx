'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/store';
import { dashboardApi } from '@/lib/api';
import { BarChart, BarChartPoint } from '@/components/bar-chart';
import { HBarChart } from '@/components/bar-chart-h';

// Kolory serii sprawdzone pod kątem czytelności i rozróżnialności przy zaburzeniach
// widzenia barw (osobna seria na wykres, więc bez legendy — tytuł karty ją nazywa).
const KOLOR_PARSOWANIE = '#2563eb';  // niebieski aplikacji
const KOLOR_ZAPYTANIA = '#0f8a5f';   // zieleń

export default function DashboardPage() {
  const { user } = useAuth();

  // users = null dla zwykłego użytkownika (backend nie zwraca liczby kont)
  const [stats, setStats] = useState<{
    users: number | null; documents: number; folders: number; processed: number;
  }>({ users: null, documents: 0, folders: 0, processed: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<BarChartPoint[]>([]);
  const [queries, setQueries] = useState<BarChartPoint[]>([]);
  const [scope, setScope] = useState<'all' | 'own'>('own');
  const [chartsLoading, setChartsLoading] = useState(true);
  // Rozbicie na użytkowników: endpoint odpowiada tylko administratorowi (403 dla reszty),
  // więc pusta lista = sekcja nie jest w ogóle rysowana.
  const [wgUzytkownikow, setWgUzytkownikow] = useState<
    { user_id: number; name: string; parsed: number; queries: number }[]
  >([]);

  useEffect(() => {
    dashboardApi.activity(30)
      .then((d) => {
        setParsed(d.days.map((day, i) => ({ day, value: d.parsed[i] ?? 0 })));
        setQueries(d.days.map((day, i) => ({ day, value: d.queries[i] ?? 0 })));
        setScope(d.scope);
      })
      .catch(() => { /* wykresy nie są krytyczne dla reszty dashboardu */ })
      .finally(() => setChartsLoading(false));

    dashboardApi.byUser(30)
      .then((d) => setWgUzytkownikow(d?.users || []))
      .catch(() => { /* 403 dla nie-admina — sekcja po prostu się nie pokazuje */ });
  }, []);

  const suma = (p: BarChartPoint[]) => p.reduce((a, b) => a + b.value, 0);

  /** Dane jednego wykresu wg użytkowników: od największej wartości, licząc od góry. */
  const wgWartosci = (wartosc: (u: { parsed: number; queries: number }) => number) =>
    wgUzytkownikow
      .map((u) => ({ label: u.name, value: wartosc(u) }))
      // przy równych wartościach alfabetycznie — inaczej kolejność zmieniałaby się losowo
      .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, 'pl'));
  // Wykresy mają różny zakres dla zwykłego użytkownika: pliki widzi te, do których
  // ma dostęp, a zapytania wyłącznie własne — stąd dwa osobne opisy.
  const opisPlikow = scope === 'all' ? 'wszyscy użytkownicy' : 'dostępne dla Ciebie';
  const opisZapytan = scope === 'all' ? 'wszyscy użytkownicy' : 'Twoje zapytania';

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await dashboardApi.stats();
        setStats({
          users: data.users ?? null,
          documents: data.documents ?? 0,
          folders: data.folders ?? 0,
          processed: data.processed ?? 0,
        });
      } catch (err: any) {
        setError(err.message || 'Nie udało się załadować statystyk');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  const isAdmin = user?.role === 'admin';

  // Kafelek bez `href` jest tylko liczbą — nie udaje odnośnika (brak kursora
  // i reakcji na najechanie). Kolejka plików leży w Administracji, więc kafelek
  // „Przetworzone" prowadzi tam wyłącznie administratora.
  const statItems: { label: string; value: string; suffix?: string; href?: string }[] = [
    // kafelek Użytkownicy tylko dla admina — prowadzi do strony administracyjnej
    ...(stats.users !== null
      ? [{ label: 'Użytkownicy', value: String(stats.users), href: '/dashboard/users' }]
      : []),
    { label: 'Dokumenty', value: String(stats.documents), href: '/dashboard/files' },
    { label: 'Foldery', value: String(stats.folders), href: '/dashboard/files' },
    {
      label: 'Przetworzone',
      value: String(stats.processed),
      // Udział przetworzonych w całości. Bez dokumentów procent nie istnieje —
      // pokazywanie „0,00%" sugerowałoby, że coś czeka na przetworzenie.
      suffix: stats.documents > 0
        ? `(${((stats.processed / stats.documents) * 100).toLocaleString('pl-PL', {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
          })}%)`
        : undefined,
      href: isAdmin ? '/dashboard/file-queue' : undefined,
    },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>

      {/* Error */}
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
        </div>
      )}

      {/* Stats */}
      {/* liczba kolumn = liczba kafelków, żeby brak kafelka Użytkownicy nie zostawiał luki */}
      <div className={`grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 ${
        statItems.length === 4 ? 'lg:grid-cols-4' : 'lg:grid-cols-3'
      }`}>
        {statItems.map((stat) => {
          const Kafelek = stat.href ? 'a' : 'div';
          return (
          <Kafelek
            key={stat.label}
            {...(stat.href ? { href: stat.href } : {})}
            className={`bg-white p-4 rounded-lg shadow-sm border border-gray-200${
              stat.href ? ' hover:shadow-md transition-shadow' : ''
            }`}
          >
            <p className="text-sm text-gray-500">{stat.label}</p>
            <p className="text-2xl font-bold text-gray-800">
              {loading ? '...' : stat.value}
              {!loading && stat.suffix && (
                <span className="ml-2 text-base font-medium text-gray-400">{stat.suffix}</span>
              )}
            </p>
          </Kafelek>
          );
        })}
      </div>

      {/* Wykresy aktywności — ostatnie 30 dni */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">Statystyki parsowania</h2>
            <span className="text-xs text-gray-400">30 dni · {opisPlikow}</span>
          </div>
          {chartsLoading ? (
            <div className="h-56 flex items-center justify-center text-sm text-gray-400">Ładowanie…</div>
          ) : (
            <>
              <p className="text-2xl font-bold text-gray-800 mb-4">{suma(parsed)}</p>
              <BarChart
                data={parsed}
                color={KOLOR_PARSOWANIE}
                unitLabel="sparsowanych plików"
                emptyText="Brak sparsowanych plików w ostatnich 30 dniach"
              />
            </>
          )}
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">Statystyki zapytań w chacie</h2>
            <span className="text-xs text-gray-400">30 dni · {opisZapytan}</span>
          </div>
          {chartsLoading ? (
            <div className="h-56 flex items-center justify-center text-sm text-gray-400">Ładowanie…</div>
          ) : (
            <>
              <p className="text-2xl font-bold text-gray-800 mb-4">{suma(queries)}</p>
              <BarChart
                data={queries}
                color={KOLOR_ZAPYTANIA}
                unitLabel="zapytań"
                emptyText="Brak zapytań w ostatnich 30 dniach"
              />
            </>
          )}
        </div>
      </div>

      {/* Rozbicie na użytkowników — tylko dla administratora */}
      {wgUzytkownikow.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">Sparsowane pliki wg użytkowników</h2>
              <span className="text-xs text-gray-400">ostatnie 30 dni</span>
            </div>
            <HBarChart
              data={wgWartosci((u) => u.parsed)}
              color={KOLOR_PARSOWANIE}
              unitLabel="sparsowanych plików"
              emptyText="Nikt nie wysłał plików w ostatnich 30 dniach"
            />
          </div>

          <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">Zapytania wg użytkowników</h2>
              <span className="text-xs text-gray-400">ostatnie 30 dni</span>
            </div>
            <HBarChart
              data={wgWartosci((u) => u.queries)}
              color={KOLOR_ZAPYTANIA}
              unitLabel="zapytań"
              emptyText="Nikt nie zadał pytania w ostatnich 30 dniach"
            />
          </div>
        </div>
      )}

      {/* Dane konta przeniesione na stronę Profil (menu pod awatarem w nagłówku) —
          Dashboard pokazuje wyłącznie stan dokumentów i aktywność. */}

      {/* Coming soon */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
        <h3 className="text-lg font-medium text-blue-800 mb-2">UWAGA!</h3>
        <p className="text-blue-600 text-sm">
          To jest bezpieczna baza wiedzy, która działa na lokalnym serwerze AI bez kontaktu z siecią Internet.
        </p>
      </div>
    </div>
  );
}