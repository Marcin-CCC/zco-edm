'use client';

import { useState } from 'react';

export interface BarChartPoint {
  day: string;    // ISO, np. "2026-07-28"
  value: number;
}

interface BarChartProps {
  data: BarChartPoint[];
  /** Kolor serii (jedna seria → bez legendy, tytuł karty ją nazywa). */
  color: string;
  /** Nazwa mierzonej wielkości — używana w dymku, np. „sparsowane pliki". */
  unitLabel: string;
  emptyText?: string;
}

const fmtDay = (iso: string) => {
  const [, m, d] = iso.split('-');
  return `${d}.${m}`;
};

const fmtDayLong = (iso: string) => {
  const dt = new Date(iso + 'T00:00:00');
  return dt.toLocaleDateString('pl-PL', { day: 'numeric', month: 'long' });
};

/**
 * Wykres słupkowy dziennych liczników.
 *
 * Zgodnie z zasadami czytelności wykresów: jedna seria (bez legendy — tytuł karty
 * nazywa wielkość), słupki zaokrąglone tylko od strony wartości i osadzone na wspólnej
 * linii bazowej, 2 px przerwy w kolorze tła między sąsiadami, recesywna siatka,
 * podpisy osi X co kilka dni (30 etykiet by się zlało), wartości pokazywane w dymku
 * po najechaniu — nie na każdym słupku.
 */
export function BarChart({ data, color, unitLabel, emptyText = 'Brak danych z tego okresu' }: BarChartProps) {
  const [hover, setHover] = useState<number | null>(null);

  const max = Math.max(...data.map((d) => d.value), 0);
  const hasData = max > 0;
  const scaleMax = hasData ? max : 1;
  // Etykiety osi X: pierwszy, ostatni i co ~5 dni — bez kolizji przy 30 słupkach
  const labelEvery = Math.max(1, Math.round(data.length / 6));

  if (!data.length) {
    return <div className="h-56 flex items-center justify-center text-sm text-gray-400">{emptyText}</div>;
  }

  return (
    <div>
      <div className="relative flex gap-2">
        {/* Oś Y: tylko trzy poziomy, tekstem drugorzędnym */}
        <div className="w-8 h-48 flex flex-col justify-between text-[11px] text-gray-400 text-right shrink-0">
          <span>{scaleMax}</span>
          <span>{Math.round(scaleMax / 2)}</span>
          <span>0</span>
        </div>

        <div className="relative flex-1">
          {/* Siatka: linie włosowe, ciągłe, cofnięte wizualnie */}
          <div className="absolute inset-0 h-48 flex flex-col justify-between pointer-events-none">
            <div className="border-t border-gray-200" />
            <div className="border-t border-gray-200" />
            <div className="border-t border-gray-300" />
          </div>

          {/* Słupki — wspólna linia bazowa, 2 px przerwy między sąsiadami */}
          <div className="relative h-48 flex items-end gap-[2px]">
            {data.map((d, i) => {
              const h = d.value > 0 ? Math.max((d.value / scaleMax) * 100, 1.5) : 0;
              return (
                <div
                  key={d.day}
                  className="flex-1 h-full flex items-end max-w-[24px] cursor-default"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  aria-label={`${fmtDayLong(d.day)}: ${d.value} ${unitLabel}`}
                >
                  <div
                    className="w-full rounded-t-[4px] transition-opacity"
                    style={{
                      height: `${h}%`,
                      backgroundColor: color,
                      opacity: hover === null || hover === i ? 1 : 0.45,
                    }}
                  />
                </div>
              );
            })}
          </div>

          {/* Podpisy osi X — co kilka dni */}
          <div className="flex gap-[2px] mt-1.5">
            {data.map((d, i) => (
              <div key={d.day} className="flex-1 max-w-[24px] text-center">
                {i % labelEvery === 0 || i === data.length - 1 ? (
                  <span className="text-[10px] text-gray-400">{fmtDay(d.day)}</span>
                ) : null}
              </div>
            ))}
          </div>

          {/* Dymek z wartością — warstwa hover zamiast liczby na każdym słupku */}
          {hover !== null && (
            <div className="absolute -top-1 left-0 right-0 flex justify-center pointer-events-none">
              <div className="bg-gray-900 text-white text-xs rounded-md px-2 py-1 shadow-lg whitespace-nowrap">
                <span className="font-medium">{data[hover].value}</span>{' '}
                <span className="text-gray-300">{unitLabel}</span>
                <span className="text-gray-400"> · {fmtDayLong(data[hover].day)}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {!hasData && (
        <p className="text-sm text-gray-400 text-center mt-3">{emptyText}</p>
      )}
    </div>
  );
}
