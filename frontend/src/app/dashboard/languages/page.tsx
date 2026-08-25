'use client';

/** Zakładka „Języki" — poprawianie tłumaczeń interfejsu bez wydawania nowej wersji.
 *
 * Skąd biorą się dane na tej stronie. Katalogi `messages/*.json` jadą z obrazem
 * aplikacji i front ma je u siebie — dlatego to TU powstaje zestawienie „co jest
 * przetłumaczone, a co nie". Backend zna wyłącznie poprawki wpisane przez człowieka
 * i nie musi znać katalogów; gdyby je kopiować do jego obrazu, byłyby dwie prawdy
 * rozjeżdżające się przy pierwszym wydaniu.
 *
 * Napis bez tłumaczenia NIE psuje ekranu — widać wtedy polskie zdanie, bo katalog
 * języka jest dokładany na polski. Dlatego lista musi wprost pokazywać, które
 * pozycje tak wypadają: inaczej nikt by ich nie znalazł.
 */
import { useTranslations } from 'next-intl';
import { useEffect, useMemo, useState } from 'react';

import { Badge, Button, Card, EmptyState, PageHeader, Table, Td, Th, inputClass } from '@/components/ui/primitives';
import { BASE_LOCALE, LOCALES, LOCALE_NAMES, type Locale } from '@/i18n/locales';
import { translationsApi, type TranslationMeta } from '@/lib/api';
import { useAuth } from '@/lib/store';

import bazowy from '../../../../messages/pl.json';
import angielski from '../../../../messages/en.json';
import czeski from '../../../../messages/cs.json';
import niemiecki from '../../../../messages/de.json';
import hiszpanski from '../../../../messages/es.json';
import ukrainski from '../../../../messages/uk.json';

/** Katalogi z obrazu, po kodzie języka. Import musi być statyczny: to komponent
 *  kliencki, a `import()` po zmiennej nie da się spakować przy budowie.
 *  Nowy język = plik w `messages/`, wpis tutaj i kod w `LOCALES`. */
const KATALOGI: Record<string, unknown> = {
  pl: bazowy,
  en: angielski,
  cs: czeski,
  de: niemiecki,
  es: hiszpanski,
  uk: ukrainski,
};

type Wpis = {
  klucz: string;
  zrodlowy: string;
  zKatalogu: string | null;
  poprawka: TranslationMeta | null;
};

type Filtr = 'wszystkie' | 'brakujace' | 'maszynowe' | 'poprawione';

/** Spłaszczenie zagnieżdżonego katalogu do kluczy z kropkami. */
function splaszcz(obiekt: unknown, przedrostek = ''): Record<string, string> {
  const wynik: Record<string, string> = {};
  if (typeof obiekt !== 'object' || obiekt === null) return wynik;
  for (const [k, v] of Object.entries(obiekt as Record<string, unknown>)) {
    const pelny = przedrostek ? `${przedrostek}.${k}` : k;
    if (typeof v === 'string') wynik[pelny] = v;
    else Object.assign(wynik, splaszcz(v, pelny));
  }
  return wynik;
}

export default function LanguagesPage() {
  const t = useTranslations('languages');
  const { user } = useAuth();
  const tlumaczone = LOCALES.filter((l) => l !== BASE_LOCALE);
  const [jezyk, setJezyk] = useState<Locale>(tlumaczone[0]);
  const [poprawki, setPoprawki] = useState<Record<string, TranslationMeta>>({});
  const [ladowanie, setLadowanie] = useState(true);
  const [tlumaczenie, setTlumaczenie] = useState(false);
  const [komunikat, setKomunikat] = useState('');
  const [blad, setBlad] = useState('');
  const [filtr, setFiltr] = useState<Filtr>('wszystkie');
  const [szukaj, setSzukaj] = useState('');
  const [szkice, setSzkice] = useState<Record<string, string>>({});

  const zrodlowe = useMemo(() => splaszcz(bazowy), []);
  const zKatalogu = useMemo(() => splaszcz(KATALOGI[jezyk]), [jezyk]);

  useEffect(() => {
    let aktualne = true;
    setLadowanie(true);
    setBlad('');
    translationsApi
      .meta(jezyk)
      .then((d) => { if (aktualne) { setPoprawki(d); setSzkice({}); } })
      .catch((e) => { if (aktualne) setBlad(e.message || t('errLoad')); })
      .finally(() => { if (aktualne) setLadowanie(false); });
    return () => { aktualne = false; };
  }, [jezyk]);

  const wpisy: Wpis[] = useMemo(
    () =>
      Object.keys(zrodlowe)
        .sort()
        .map((klucz) => ({
          klucz,
          zrodlowy: zrodlowe[klucz],
          zKatalogu: zKatalogu[klucz] ?? null,
          poprawka: poprawki[klucz] ?? null,
        })),
    [zrodlowe, zKatalogu, poprawki],
  );

  /** Napis, który użytkownik zobaczy DZIŚ: poprawka → katalog → polski (zapas). */
  const obowiazujacy = (w: Wpis) => w.poprawka?.value ?? w.zKatalogu ?? w.zrodlowy;
  const brakuje = (w: Wpis) => !w.poprawka && !w.zKatalogu;

  const widoczne = useMemo(() => {
    const fraza = szukaj.trim().toLowerCase();
    return wpisy.filter((w) => {
      if (filtr === 'brakujace' && !brakuje(w)) return false;
      if (filtr === 'maszynowe' && w.poprawka?.source !== 'machine') return false;
      if (filtr === 'poprawione' && w.poprawka?.source !== 'human') return false;
      if (!fraza) return true;
      return (
        w.klucz.toLowerCase().includes(fraza) ||
        w.zrodlowy.toLowerCase().includes(fraza) ||
        obowiazujacy(w).toLowerCase().includes(fraza)
      );
    });
  }, [wpisy, filtr, szukaj]);

  const liczbaBrakow = useMemo(() => wpisy.filter(brakuje).length, [wpisy]);
  const liczbaMaszynowych = useMemo(
    () => wpisy.filter((w) => w.poprawka?.source === 'machine').length,
    [wpisy],
  );

  async function zapisz(w: Wpis, wartosc: string) {
    const nowa = wartosc.trim();
    if (nowa === (w.poprawka?.value ?? '')) return;         // nic się nie zmieniło
    setBlad('');
    try {
      await translationsApi.save(jezyk, w.klucz, nowa);
      setPoprawki((p) => {
        const kopia = { ...p };
        if (nowa) kopia[w.klucz] = { value: nowa, source: 'human', updated_at: null };
        else delete kopia[w.klucz];
        return kopia;
      });
      setSzkice((s) => { const kopia = { ...s }; delete kopia[w.klucz]; return kopia; });
    } catch (e: any) {
      setBlad(e.message || t('errSave'));
    }
  }

  /** Tłumaczenie maszynowe — TYLKO tego, czego nie ma. Gotowych nie ruszamy:
   *  napis sprawdzony przez człowieka nie może zniknąć pod przebiegiem modelu. */
  async function przetlumaczBrakujace() {
    const brakujace = wpisy.filter(brakuje).map((w) => ({ key: w.klucz, source: w.zrodlowy }));
    if (!brakujace.length) return;
    setTlumaczenie(true);
    setKomunikat('');
    setBlad('');
    try {
      const wynik = await translationsApi.auto(jezyk, brakujace);
      const swieze = await translationsApi.meta(jezyk);
      setPoprawki(swieze);
      const ile = Object.keys(wynik.translated).length;
      setKomunikat(
        wynik.failed.length
          ? t('doneSome', { done: ile, failed: wynik.failed.length })
          : t('doneAll', { done: ile }),
      );
    } catch (e: any) {
      setBlad(e.message || t('errAuto'));
    } finally {
      setTlumaczenie(false);
    }
  }

  if (!user?.is_admin) {
    return <EmptyState title={t('noAccess')} hint={t('noAccessHint')} />;
  }

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Button onClick={przetlumaczBrakujace} disabled={tlumaczenie || !liczbaBrakow}>
            {tlumaczenie ? t('translating') : t('translateMissing', { count: liczbaBrakow })}
          </Button>
        }
      />

      <Card className="mb-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-app-muted">
            {t('language')}
            <select
              value={jezyk}
              onChange={(e) => setJezyk(e.target.value as Locale)}
              className={`${inputClass} ml-2 w-auto`}
            >
              {tlumaczone.map((l) => (
                <option key={l} value={l}>
                  {l.toUpperCase()} — {LOCALE_NAMES[l]}
                </option>
              ))}
            </select>
          </label>

          <div className="flex flex-wrap gap-1">
            {([
              ['wszystkie', t('filterAll', { count: wpisy.length })],
              ['brakujace', t('filterMissing', { count: liczbaBrakow })],
              ['maszynowe', t('filterMachine', { count: liczbaMaszynowych })],
              ['poprawione', t('filterHuman')],
            ] as [Filtr, string][]).map(([klucz, etykieta]) => (
              <Button
                key={klucz}
                small
                variant={filtr === klucz ? 'primary' : 'default'}
                onClick={() => setFiltr(klucz)}
              >
                {etykieta}
              </Button>
            ))}
          </div>

          <input
            value={szukaj}
            onChange={(e) => setSzukaj(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className={`${inputClass} max-w-xs`}
          />
        </div>
      </Card>

      {blad && (
        <div className="mb-4 rounded-ctl border border-app-line bg-app-dangerbg px-4 py-3 text-sm text-app-danger">
          {blad}
        </div>
      )}
      {komunikat && (
        <div className="mb-4 rounded-ctl border border-app-line bg-app-greenbg px-4 py-3 text-sm text-[#148a57]">
          {komunikat}
        </div>
      )}

      <Card>
        {ladowanie ? (
          <div className="p-6 text-sm text-app-muted">{t('loading')}</div>
        ) : !widoczne.length ? (
          <EmptyState title={t('nothingHere')} hint={t('nothingHereHint')} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t('colKey')}</Th>
                <Th>{t('colSource')}</Th>
                <Th>{LOCALE_NAMES[jezyk]}</Th>
                <Th>{t('colState')}</Th>
              </tr>
            </thead>
            <tbody>
              {widoczne.map((w) => {
                const wartosc = szkice[w.klucz] ?? w.poprawka?.value ?? w.zKatalogu ?? '';
                return (
                  <tr key={w.klucz} className="hover:bg-app-hover">
                    <Td>
                      <code className="text-[12px] text-app-muted">{w.klucz}</code>
                    </Td>
                    <Td>{w.zrodlowy}</Td>
                    <Td>
                      <input
                        value={wartosc}
                        onChange={(e) => setSzkice((s) => ({ ...s, [w.klucz]: e.target.value }))}
                        onBlur={(e) => zapisz(w, e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                        placeholder={w.zrodlowy}
                        className={inputClass}
                      />
                    </Td>
                    <Td>
                      {brakuje(w) ? (
                        <Badge tone="danger">{t('stateMissing')}</Badge>
                      ) : w.poprawka?.source === 'machine' ? (
                        <Badge tone="purple">{t('stateMachine')}</Badge>
                      ) : w.poprawka ? (
                        <Badge tone="green">{t('stateHuman')}</Badge>
                      ) : (
                        <Badge tone="gray">{t('stateCatalog')}</Badge>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>

      <p className="mt-3 text-xs text-app-muted">
        {t('footer')}
      </p>
    </div>
  );
}
