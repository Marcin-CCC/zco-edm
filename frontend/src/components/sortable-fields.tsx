'use client';

/** Lista pól nagłówkowych z kolejnością zmienianą przeciąganiem.
 *
 * Kolejność NIE jest kosmetyką: w tej samej kolejności wychodzą kolumny przy
 * pobieraniu listy dokumentów do arkusza (zob. backend/app/eksport.py). Układ
 * arkusza ustawia się więc tam, gdzie i tak definiuje się pola.
 *
 * Poprzednia wersja miała strzałki góra/dół. Makieta 1.5 przewiduje wyłącznie
 * uchwyt do przeciągania — ale samo przeciąganie odcięłoby obsługę z klawiatury,
 * więc uchwyt jest przyciskiem i reaguje na strzałki po ustawieniu na nim
 * fokusu. Przeciąganie dla myszy, strzałki dla klawiatury, jeden uchwyt.
 */
import { useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';

import { IconGrip } from '@/components/icons';

interface Props<T> {
  items: T[];
  onReorder: (items: T[]) => void;
  /** Treść wiersza (pola formularza) — bez uchwytu, ten dokłada komponent. */
  renderItem: (item: T, index: number) => ReactNode;
  klucz: (item: T, index: number) => string;
}

export function SortableFields<T>({ items, onReorder, renderItem, klucz }: Props<T>) {
  const t = useTranslations('common');
  const [zrodlo, setZrodlo] = useState<number | null>(null);
  const [nadKtorym, setNadKtorym] = useState<number | null>(null);
  const [przeciagalny, setPrzeciagalny] = useState<number | null>(null);

  const przenies = (z: number, na: number) => {
    if (z === na || na < 0 || na >= items.length) return;
    const kopia = [...items];
    const [wyjety] = kopia.splice(z, 1);
    kopia.splice(na, 0, wyjety);
    onReorder(kopia);
  };

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div
          key={klucz(item, i)}
          // `draggable` włączamy dopiero po chwyceniu uchwytu — inaczej próba
          // zaznaczenia tekstu w polu formularza zaczynałaby przeciąganie wiersza.
          draggable={przeciagalny === i}
          onDragStart={(e) => {
            setZrodlo(i);
            e.dataTransfer.effectAllowed = 'move';
          }}
          onDragOver={(e) => {
            if (zrodlo === null) return;
            e.preventDefault();
            setNadKtorym(i);
          }}
          onDrop={(e) => {
            e.preventDefault();
            if (zrodlo !== null) przenies(zrodlo, i);
            setZrodlo(null);
            setNadKtorym(null);
            setPrzeciagalny(null);
          }}
          onDragEnd={() => { setZrodlo(null); setNadKtorym(null); setPrzeciagalny(null); }}
          className={[
            'flex flex-wrap items-start gap-2 rounded-ctl border p-2 transition-colors',
            zrodlo === i ? 'opacity-50' : '',
            nadKtorym === i && zrodlo !== null && zrodlo !== i
              ? 'border-app-blue bg-[#eef4ff]'
              : 'border-transparent',
          ].join(' ')}
        >
          <button
            type="button"
            title={t('reorderHint')}
            aria-label={`Zmień kolejność pozycji ${i + 1}`}
            onMouseDown={() => setPrzeciagalny(i)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowUp') { e.preventDefault(); przenies(i, i - 1); }
              if (e.key === 'ArrowDown') { e.preventDefault(); przenies(i, i + 1); }
            }}
            className="mt-2 cursor-grab text-app-muted hover:text-app-text active:cursor-grabbing"
          >
            <IconGrip size={16} />
          </button>
          {renderItem(item, i)}
        </div>
      ))}
    </div>
  );
}
