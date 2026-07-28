'use client';

import { useState } from 'react';

export interface HBarPoint {
  label: string;   // nazwa użytkownika
  value: number;
}

interface HBarChartProps {
  data: HBarPoint[];
  /** Kolor serii (jedna seria → bez legendy, tytuł karty ją nazywa). */
  color: string;
  /** Nazwa mierzonej wielkości — używana w dymku, np. „sparsowane pliki". */
  unitLabel: string;
  emptyText?: string;
}

/**
 * Górna granica osi i podziałka złożona wyłącznie z liczb całkowitych — wykres
 * pokazuje sztuki (pliki, zapytania), więc „12.5 pliku" byłoby bez sensu.
 */
function osX(max: number): { skala: number; podzialka: number[] } {
  if (max <= 0) return { skala: 1, podzialka: [0, 1] };
  const rzad = Math.pow(10, Math.floor(Math.log10(max)));
  let skala = 10 * rzad;
  for (const k of [1, 2, 2.5, 5, 10]) {
    if (max <= k * rzad) { skala = k * rzad; break; }
  }
  skala = Math.ceil(skala);
  // Tyle działek, ile daje się podzielić bez ułamków (4 → 2 → brak podziału)
  const krokow = [4, 2].find((n) => skala % n === 0) ?? 1;
  const podzialka = Array.from({ length: krokow + 1 }, (_, i) => (skala / krokow) * i);
  return { skala, podzialka };
}

/**
 * Poziomy wykres słupkowy — porównanie wartości między nazwanymi pozycjami.
 *
 * Poziomy układ wybrany świadomie: nazwiska na osi pionowej czyta się wprost,
 * bez obracania etykiet, a lista pozycji może rosnąć bez ściskania słupków.
 * Reszta zasad jak na wykresie dziennym: jedna seria bez legendy, słupki
 * zaokrąglone od strony wartości i osadzone na wspólnej linii bazowej, recesywna
 * siatka, wartości w dymku po najechaniu — nie przy każdym słupku.
 */
export function HBarChart({ data, color, unitLabel, emptyText = 'Brak danych z tego okresu' }: HBarChartProps) {
  const [hover, setHover] = useState<number | null>(null);

  const max = Math.max(...data.map((d) => d.value), 0);
  const { skala, podzialka } = osX(max);

  if (!data.length) {
    return <div className="h-40 flex items-center justify-center text-sm text-gray-400">{emptyText}</div>;
  }

  return (
    <div className="relative">
      <div className="flex gap-3">
        {/* Oś Y: nazwy pozycji, tekstem drugorzędnym */}
        <div className="w-32 shrink-0 flex flex-col justify-around gap-[3px] py-[1px]">
          {data.map((d, i) => (
            <div
              key={d.label}
              className="h-5 flex items-center justify-end text-[11px] leading-tight text-right truncate"
              style={{ color: hover === i ? '#0f172a' : '#64748b' }}
              title={d.label}
            >
              {d.label}
            </div>
          ))}
        </div>

        <div className="relative flex-1">
          {/* Siatka pionowa — linie włosowe, oś zerowa mocniejsza */}
          <div className="absolute inset-0 flex justify-between pointer-events-none">
            {podzialka.map((v, i) => (
              <div key={v} className={i === 0 ? 'border-l border-gray-300' : 'border-l border-gray-200'} />
            ))}
          </div>

          {/* Słupki — wspólna linia bazowa po lewej, 3 px przerwy między sąsiadami */}
          <div className="relative flex flex-col justify-around gap-[3px] py-[1px]">
            {data.map((d, i) => {
              const szerokosc = d.value > 0 ? Math.max((d.value / skala) * 100, 0.8) : 0;
              return (
                <div
                  key={d.label}
                  className="h-5 flex items-center cursor-default"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  aria-label={`${d.label}: ${d.value} ${unitLabel}`}
                >
                  <div
                    className="h-3 rounded-r-[4px] transition-opacity"
                    style={{
                      width: `${szerokosc}%`,
                      backgroundColor: color,
                      opacity: hover === null || hover === i ? 1 : 0.45,
                    }}
                  />
                </div>
              );
            })}
          </div>

          {/* Podpisy osi X */}
          <div className="relative mt-1.5 h-4">
            {podzialka.map((v, i) => (
              <span
                key={v}
                className="absolute text-[10px] text-gray-400 -translate-x-1/2"
                style={{ left: `${(i / (podzialka.length - 1)) * 100}%` }}
              >
                {v}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Dymek z wartością — jeden na wykres, zamiast liczby przy każdym słupku */}
      {hover !== null && (
        <div className="absolute top-0 right-0 pointer-events-none">
          <div className="bg-gray-900 text-white text-xs rounded-md px-2 py-1 shadow-lg whitespace-nowrap">
            <span className="font-medium">{data[hover].value}</span>{' '}
            <span className="text-gray-300">{unitLabel}</span>
            <span className="text-gray-400"> · {data[hover].label}</span>
          </div>
        </div>
      )}

      {max === 0 && <p className="text-sm text-gray-400 text-center mt-3">{emptyText}</p>}
    </div>
  );
}
