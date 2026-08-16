'use client';

/** Elementy powtarzalne layoutu 1.5 — jedno miejsce, w którym mieszkają wartości wizualne.
 *
 * Każdy ekran składa się z tych samych klocków: nagłówek strony, karta, tabela,
 * przycisk, plakietka statusu, akcje w wierszu. Trzymanie ich osobno oznaczałoby
 * jedenaście kopii tych samych klas — a przy pierwszej korekcie promienia rogu
 * dziesięć z nich zostałoby po staremu.
 *
 * Zasada z makiety: NIEBIESKI JEST KOLOREM AKCJI. Stanu (aktywna zakładka, bieżąca
 * strona, wybrany widok) nie oznaczamy niebieskim wypełnieniem — od tego są
 * neutralne tła.
 */
import { useEffect } from 'react';
import type { ButtonHTMLAttributes, ReactNode, TdHTMLAttributes } from 'react';

import { IconClose } from '@/components/icons';

/* ---------------------------------------------------------------- nagłówek */

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="m-0 text-[28px] font-bold tracking-[-.3px] text-app-text">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-app-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------- karta */

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-card border border-app-line bg-app-card shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 border-b border-app-line px-[18px] py-[14px] ${className}`}>
      {children}
    </div>
  );
}

/* --------------------------------------------------------------- przyciski */

type Wariant = 'primary' | 'default' | 'ghost' | 'danger';

const WARIANTY: Record<Wariant, string> = {
  primary: 'bg-app-blue border-app-blue text-white hover:bg-app-blue2 hover:border-app-blue2 active:bg-[var(--app-blue-active)]',
  default: 'bg-white border-app-line text-app-text hover:bg-app-hover',
  ghost: 'border-transparent bg-transparent text-app-blue hover:bg-[#eef4ff]',
  danger: 'bg-white border-[#fecdd3] text-app-danger hover:bg-app-dangerbg',
};

export function Button({
  variant = 'default',
  small = false,
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Wariant; small?: boolean }) {
  return (
    <button
      className={[
        'inline-flex items-center gap-[7px] whitespace-nowrap rounded-ctl border font-bold transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-app-blue',
        'disabled:cursor-not-allowed disabled:opacity-50',
        small ? 'px-2.5 py-[7px] text-xs' : 'px-3.5 py-2.5 text-sm',
        WARIANTY[variant],
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </button>
  );
}

/** Kwadratowy przycisk akcji w wierszu — pojawia się dopiero po najechaniu.
 *
 * Kolory z makiety niosą znaczenie: zielony edytuje, niebieski dotyczy uprawnień,
 * czerwony usuwa. `tone` nie jest ozdobą, tylko informacją.
 */
export function IconButton({
  tone = 'neutral',
  title,
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: 'edit' | 'lock' | 'action' | 'danger' | 'neutral';
  title: string;
}) {
  const tony = {
    edit: 'text-app-green hover:bg-app-greenbg',
    lock: 'text-app-blue hover:bg-[#eaf1ff]',
    // Ten sam błękit co „lock", ale inna nazwa: „lock" znaczy „uprawnienia",
    // a „action" — zwykła czynność na wierszu (pobierz, przenieś). Gdyby dzieliły
    // klucz, pierwsza zmiana koloru uprawnień przemalowałaby też pobieranie.
    action: 'text-app-blue hover:bg-[#eaf1ff]',
    danger: 'text-app-danger hover:bg-app-dangerbg',
    neutral: 'text-app-muted hover:bg-app-hover',
  };
  return (
    <button
      title={title}
      aria-label={title}
      className={`grid h-[30px] w-[30px] place-items-center rounded-lg border border-app-line bg-white transition-colors ${tony[tone]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

/** Kontener akcji wiersza — ukryte do momentu najechania na wiersz (`group`). */
export function RowActions({ children }: { children: ReactNode }) {
  return (
    <div className="flex justify-end gap-1.5 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 focus-within:opacity-100">
      {children}
    </div>
  );
}

/* -------------------------------------------------------------- plakietki */

type Ton = 'green' | 'blue' | 'purple' | 'gray' | 'danger';

const TONY: Record<Ton, string> = {
  green: 'text-[#148a57] bg-app-greenbg',
  blue: 'text-[#2455cc] bg-[#eaf1ff]',
  purple: 'text-[#694be0] bg-[#f0ebff]',
  gray: 'text-[#65738a] bg-[#f2f4f8]',
  danger: 'text-app-danger bg-app-dangerbg',
};

export function Badge({ tone = 'gray', children }: { tone?: Ton; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-[5px] rounded-full px-[9px] py-[5px] text-[11px] font-bold ${TONY[tone]}`}>
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- tabela */

export function Table({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={`min-w-full border-collapse ${className}`}>{children}</table>
    </div>
  );
}

export function Th({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return (
    <th className={`border-b border-app-line bg-[#fafbfd] px-[14px] py-3 text-left text-[11px] uppercase tracking-[.02em] text-[#65738a] ${className}`}>
      {children}
    </th>
  );
}

export function Td({
  children,
  className = '',
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={`border-b border-app-line px-[14px] py-3 align-middle text-[13px] ${className}`} {...rest}>
      {children}
    </td>
  );
}

/** Drobny opis pod treścią komórki (np. e-mail pod nazwą użytkownika). */
export function Sub({ children }: { children: ReactNode }) {
  return <div className="mt-0.5 text-[11px] text-app-muted">{children}</div>;
}

/* ------------------------------------------------------------ stany puste */

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="px-[18px] py-10 text-center">
      <p className="text-sm font-medium text-app-text">{title}</p>
      {hint && <p className="mt-1 text-xs text-app-muted">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------- formularze */

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[13px] font-medium text-app-text">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-app-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  'h-10 w-full rounded-ctl border border-app-line bg-white px-3 text-[13px] text-app-text ' +
  'focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-app-blue';

/* ------------------------------------------------------------------- okna */

/** Okno modalne w stylu 1.5.
 *
 * Escape zamyka i kliknięcie w tło zamyka — obie drogi są odruchem, a okno bez
 * nich sprawia wrażenie zawieszonej aplikacji. Zamknięcia NIE podpinamy pod
 * kliknięcie samego okna (`stopPropagation`), bo inaczej zaznaczanie tekstu
 * kończące się poza oknem zamykałoby je w połowie czytania.
 */
export function Modal({
  title,
  onClose,
  children,
  footer,
  size = 'md',
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: 'md' | 'lg' | 'xl';
}) {
  useEffect(() => {
    const naKlawisz = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', naKlawisz);
    return () => document.removeEventListener('keydown', naKlawisz);
  }, [onClose]);

  const szerokosc = size === 'xl' ? 'max-w-2xl' : size === 'lg' ? 'max-w-lg' : 'max-w-md';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      onMouseDown={onClose}
      role="presentation"
    >
      <div
        className={`w-full ${szerokosc} max-h-[86vh] overflow-y-auto rounded-card bg-white shadow-[0_18px_50px_rgba(19,35,63,.22)]`}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between gap-3 border-b border-app-line px-5 py-4">
          <h2 className="min-w-0 break-words text-[16px] font-bold text-app-text">{title}</h2>
          <button
            onClick={onClose}
            className="-mr-1 shrink-0 rounded-ctl p-1 text-app-muted hover:bg-app-hover hover:text-app-text"
            aria-label="Zamknij"
          >
            <IconClose size={18} />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-app-line px-5 py-3">{footer}</div>
        )}
      </div>
    </div>
  );
}
