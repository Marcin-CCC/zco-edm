'use client';

/** Wykres liniowo-obszarowy dziennych liczników (makieta 1.5).
 *
 * Dlaczego linia, a nie słupki: przy zakresie 90 dni słupek miał niecałe trzy
 * piksele szerokości i wykres zamieniał się w grzebień. Linia czyta się tak samo
 * przy 7 i przy 90 punktach, a wypełnienie pod nią pokazuje wielkość zjawiska.
 *
 * Współrzędne liczymy w pikselach na podstawie zmierzonej szerokości kontenera,
 * zamiast rozciągać stałe `viewBox` przez `preserveAspectRatio="none"`. To drugie
 * jest krótsze, ale skaluje niejednorodnie i grubość linii zmienia się razem
 * z szerokością okna — przy wąskim ekranie linia robi się wyraźnie grubsza.
 */
import { useEffect, useRef, useState } from 'react';

export interface AreaChartPoint {
  day: string; // ISO, np. „2026-07-28"
  value: number;
}

interface Props {
  data: AreaChartPoint[];
  /** Kolor serii. Jedna seria na wykres → bez legendy, nazywa ją tytuł karty. */
  color: string;
  /** Nazwa mierzonej wielkości, używana w dymku (np. „sparsowanych plików"). */
  unitLabel: string;
  emptyText?: string;
}

const WYS = 155;      // wysokość pola danych
const OS_Y = 42;      // szerokość kolumny z podpisami osi Y
const MARGINES = 8;   // oddech z prawej, żeby ostatni punkt nie dotykał krawędzi
const PODPISY = 24;   // pas na daty pod wykresem

const fmtDzien = (iso: string) => {
  const [, m, d] = iso.split('-');
  return `${d}.${m}`;
};

const fmtDzienDlugi = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('pl-PL', { day: 'numeric', month: 'long' });

/** Górna granica osi zaokrąglona „do ludzkiej liczby" (1, 2, 5 × 10ⁿ).
 *  Oś kończąca się na 137 wygląda na pomyłkę, nawet gdy to prawdziwe maksimum. */
function gornaGranica(max: number): number {
  if (max <= 4) return Math.max(max, 1);
  const rzad = 10 ** Math.floor(Math.log10(max));
  for (const krok of [1, 2, 2.5, 5, 10]) {
    const kandydat = krok * rzad;
    if (kandydat >= max) return kandydat;
  }
  return 10 * rzad;
}

export function AreaChart({ data, color, unitLabel, emptyText = 'Brak danych z tego okresu' }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [szerokosc, setSzerokosc] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const obs = new ResizeObserver(([wpis]) => setSzerokosc(wpis.contentRect.width));
    obs.observe(el);
    setSzerokosc(el.getBoundingClientRect().width);
    return () => obs.disconnect();
  }, []);

  const max = Math.max(...data.map((d) => d.value), 0);
  const skala = gornaGranica(max);
  const suma = data.reduce((a, b) => a + b.value, 0);

  if (!data.length) {
    return <div className="flex h-[190px] items-center justify-center text-sm text-app-muted">{emptyText}</div>;
  }

  const pole = Math.max(szerokosc - OS_Y - MARGINES, 0);
  const krok = data.length > 1 ? pole / (data.length - 1) : 0;
  const x = (i: number) => (data.length > 1 ? i * krok : pole / 2);
  const y = (v: number) => WYS - (v / skala) * WYS;

  const punkty = data.map((d, i) => `${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join(' ');
  const obszar = `M${punkty.split(' ').join(' L')} L${pole.toFixed(1)},${WYS} L0,${WYS} Z`;

  // Podpisy osi X: pierwszy, ostatni i co ~1/6 zakresu — 30 dat by się zlało.
  const coIle = Math.max(1, Math.round(data.length / 6));

  /** Najbliższy punkt względem kursora — trafianie w linię byłoby nieznośne. */
  function najblizszy(e: React.MouseEvent<HTMLDivElement>) {
    const prostokat = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - prostokat.left - OS_Y;
    if (krok === 0) return 0;
    return Math.min(data.length - 1, Math.max(0, Math.round(px / krok)));
  }

  const opisSerii = `Wykres: ${suma} ${unitLabel} w ${data.length} dniach, od ${fmtDzienDlugi(data[0].day)} do ${fmtDzienDlugi(data[data.length - 1].day)}.`;

  return (
    <div>
      <div
        ref={box}
        className="relative"
        style={{ height: WYS + PODPISY }}
        role="img"
        aria-label={opisSerii}
        onMouseMove={(e) => setHover(najblizszy(e))}
        onMouseLeave={() => setHover(null)}
      >
        {/* Oś Y — pięć poziomów, tekstem drugorzędnym */}
        <div
          className="absolute left-0 top-0 flex flex-col justify-between text-right text-[10px] text-app-muted"
          style={{ width: OS_Y - 8, height: WYS }}
        >
          {[4, 3, 2, 1, 0].map((i) => (
            <span key={i} className="-translate-y-1/2 first:translate-y-0 last:-translate-y-full">
              {Math.round((skala * i) / 4).toLocaleString('pl-PL')}
            </span>
          ))}
        </div>

        {/* Siatka — linie włosowe, cofnięte wizualnie */}
        <div className="absolute top-0" style={{ left: OS_Y, right: MARGINES, height: WYS }}>
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="absolute left-0 right-0 border-t"
              style={{ top: (WYS * i) / 4, borderColor: i === 4 ? '#dbe3ef' : '#eef2f8' }}
            />
          ))}
        </div>

        {szerokosc > 0 && (
          <svg
            className="absolute top-0 overflow-visible"
            style={{ left: OS_Y }}
            width={pole}
            height={WYS}
            aria-hidden="true"
          >
            <path d={obszar} fill={color} fillOpacity={0.08} />
            <polyline points={punkty} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {hover !== null && (
              <>
                <line x1={x(hover)} y1={0} x2={x(hover)} y2={WYS} stroke={color} strokeWidth={1} strokeOpacity={0.35} />
                {/* Pierścień w kolorze tła oddziela znacznik od linii i od siatki */}
                <circle cx={x(hover)} cy={y(data[hover].value)} r={4.5} fill={color} stroke="#fff" strokeWidth={2} />
              </>
            )}
          </svg>
        )}

        {/* Podpisy osi X */}
        <div
          className="absolute flex justify-between text-[10px] text-app-muted"
          style={{ left: OS_Y, right: MARGINES, top: WYS + 6 }}
        >
          {data.map((d, i) =>
            i % coIle === 0 || i === data.length - 1 ? (
              <span key={d.day} className="whitespace-nowrap">{fmtDzien(d.day)}</span>
            ) : null,
          )}
        </div>

        {/* Dymek — jedna wartość naraz, zamiast liczby przy każdym punkcie */}
        {hover !== null && szerokosc > 0 && (
          <div
            className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap rounded-md bg-[#13233f] px-2 py-1 text-[11px] text-white shadow-lg"
            style={{
              left: Math.min(Math.max(OS_Y + x(hover), 60), szerokosc - 60),
              top: Math.max(y(data[hover].value) - 34, -6),
            }}
          >
            <span className="font-semibold">{data[hover].value.toLocaleString('pl-PL')}</span>{' '}
            <span className="text-[#c9d6ea]">{unitLabel}</span>
            <span className="text-[#9fb3d1]"> · {fmtDzienDlugi(data[hover].day)}</span>
          </div>
        )}
      </div>

      {max === 0 && <p className="mt-2 text-center text-sm text-app-muted">{emptyText}</p>}
    </div>
  );
}
