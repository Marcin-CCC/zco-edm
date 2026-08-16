'use client';

/** Dolny rząd Dashboardu: Szybkie akcje, Miejsce w systemie, Status systemu.
 *
 * Dwa ostatnie panele są administracyjne. Zwykły użytkownik nic nie zrobi
 * z informacją, ile wolnego miejsca ma serwer, a zajętość dysku i obciążenie
 * to dane o infrastrukturze klienta — backend odpowiada na nie 403, więc panele
 * po prostu się nie pojawiają, a Szybkie akcje zajmują całą szerokość.
 */
import Link from 'next/link';

import { Card } from '@/components/ui/primitives';
import { rozmiarPliku } from '@/components/file-type-icon';
import {
  IconChat,
  IconFilePlus,
  IconSearch,
  IconUserPlus,
} from '@/components/icons';
import type { SystemStatus } from '@/lib/api';

type IkonaKomponent = React.ComponentType<{ size?: number }>;

interface Akcja {
  label: string;
  hint: string;
  href: string;
  Icon: IkonaKomponent;
}

/** Szybkie akcje. „Dodaj użytkownika" tylko dla administratora — pozostali
 *  dostaliby odnośnik prowadzący do ekranu, który odmówi im dostępu. */
export function QuickActions({ isAdmin }: { isAdmin: boolean }) {
  const akcje: Akcja[] = [
    ...(isAdmin
      ? [{ label: 'Dodaj użytkownika', hint: 'Nowe konto', href: '/dashboard/users', Icon: IconUserPlus }]
      : []),
    { label: 'Dodaj pliki', hint: 'Prześlij dokumenty', href: '/dashboard/files', Icon: IconFilePlus },
    { label: 'Chat z AI', hint: 'Zadaj pytanie', href: '/dashboard/chat', Icon: IconChat },
    { label: 'Wyszukaj dokument', hint: 'Zbuduj zapytanie', href: '/dashboard/wyszukiwanie', Icon: IconSearch },
  ];

  return (
    <Card className="p-4">
      <h3 className="mb-3.5 text-[15px] font-bold text-app-text">Szybkie akcje</h3>
      <div className={`grid gap-3 ${akcje.length === 4 ? 'grid-cols-4' : 'grid-cols-3'}`}>
        {akcje.map(({ label, hint, href, Icon }) => (
          <Link
            key={label}
            href={href}
            className="rounded-ctl px-1 py-2 text-center transition-colors hover:bg-app-hover"
          >
            <span className="mx-auto mb-2 grid h-[42px] w-[42px] place-items-center rounded-[12px] bg-[#edf4ff] text-app-blue">
              <Icon size={21} />
            </span>
            <b className="block text-[12px] font-bold leading-tight text-app-text">{label}</b>
            <span className="mt-0.5 block text-[10px] leading-tight text-app-muted">{hint}</span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

/** Zajętość dysku serwera.
 *
 * Pierścień pokazuje CAŁY wolumen, na którym leżą dokumenty — na Sparku dzielony
 * z modelami, obrazami Dockera i n8n. Dlatego pod spodem podajemy osobno rozmiar
 * samych dokumentów: bez tego ktoś zobaczy kiedyś 80% i wywoła alarm o dokumentach,
 * gdy naprawdę urosły modele.
 */
export function StoragePanel({ stan }: { stan: SystemStatus | null }) {
  const m = stan?.magazyn;
  const procent = m?.dostepny ? (m.percent ?? 0) : null;
  // Powyżej 85% zajętości kolor przestaje być ozdobą i zaczyna być ostrzeżeniem.
  const kolor = procent !== null && procent >= 85 ? 'var(--app-danger)' : 'var(--app-blue)';

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-[15px] font-bold text-app-text">Miejsce w systemie</h3>
      <div className="flex items-center gap-[18px]">
        <div
          className="relative grid h-[100px] w-[100px] shrink-0 place-items-center rounded-full"
          style={{
            background:
              procent !== null
                ? `conic-gradient(${kolor} 0 ${procent}%, #dfe6f0 ${procent}% 100%)`
                : '#eef2f8',
          }}
        >
          <div className="absolute h-[70px] w-[70px] rounded-full bg-white" />
          <strong className="z-[1] text-[21px] text-app-text">
            {procent !== null ? `${procent.toLocaleString('pl-PL', { maximumFractionDigits: 0 })}%` : '—'}
          </strong>
        </div>
        <div className="min-w-0">
          {m?.dostepny ? (
            <>
              <div className="text-[12px] text-app-muted">
                Wolne <b className="text-app-text">{rozmiarPliku(m.free)}</b> z {rozmiarPliku(m.total)}
              </div>
              <div className="mt-2 text-[11px] leading-relaxed text-app-muted">
                Dysk serwera dzielony z pozostałymi usługami.
                <br />
                Same dokumenty: <b className="text-app-text">{rozmiarPliku(m.documents_bytes)}</b>
              </div>
            </>
          ) : (
            <div className="text-[12px] text-app-muted">Nie udało się odczytać zajętości dysku.</div>
          )}
          <Link
            href="/dashboard/files"
            className="mt-3 inline-block text-[11px] font-bold text-app-blue hover:underline"
          >
            Zarządzaj miejscem ›
          </Link>
        </div>
      </div>
    </Card>
  );
}

function Wiersz({ nazwa, online, opis }: { nazwa: string; online: boolean; opis?: string | null }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-app-line pb-2 last:border-b-0 last:pb-0">
      <span className="min-w-0">
        <span className="block text-[12px] text-app-text">{nazwa}</span>
        {opis && <span className="mt-0.5 block text-[11px] text-app-muted">{opis}</span>}
      </span>
      <span className={`shrink-0 text-[12px] font-bold ${online ? 'text-app-green' : 'text-app-danger'}`}>
        ● {online ? 'Online' : 'Offline'}
      </span>
    </div>
  );
}

/** Stan usług, na których stoi aplikacja.
 *
 * Zamiast czterech zielonych kropek każdy wiersz niesie konkret — bo panel,
 * który zawsze pokazuje to samo, przestaje być czytany. Przy modelu podajemy
 * długość kolejki, a nie procent GPU: chwilowy odczyt karty skacze między 0
 * a 100 w ciągu sekundy i nie odpowiada na pytanie „czy serwer jest zajęty".
 */
export function SystemStatusPanel({ stan, blad }: { stan: SystemStatus | null; blad: boolean }) {
  const opisParsera = () => {
    if (!stan) return null;
    const p = stan.parser;
    if (!p.docling && !p.model) return 'Docling i model nie odpowiadają';
    if (!p.docling) return 'Docling nie odpowiada';
    if (!p.model) return 'Model językowy nie odpowiada';
    if (p.running === null) return 'model odpowiada';
    if (p.running === 0 && !p.waiting) return 'model bezczynny';
    return `model liczy ${p.running}${p.waiting ? `, czeka ${p.waiting}` : ''}`;
  };

  const opisAplikacji = () => {
    const a = stan?.aplikacja;
    if (!a || a.load_percent === null) return null;
    return `obciążenie ${a.load_percent.toLocaleString('pl-PL', { maximumFractionDigits: 0 })}% z ${a.cores} rdzeni`;
  };

  const opisMagazynu = () => {
    const m = stan?.magazyn;
    if (!m?.dostepny) return null;
    return `${rozmiarPliku(m.free)} wolnego`;
  };

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-[15px] font-bold text-app-text">Status systemu</h3>
      {blad || !stan ? (
        <p className="text-[12px] text-app-muted">
          {blad ? 'Nie udało się odczytać stanu serwera.' : 'Odczyt stanu…'}
        </p>
      ) : (
        <div className="grid gap-2.5">
          <Wiersz nazwa="Aplikacja" online={stan.aplikacja.online} opis={opisAplikacji()} />
          <Wiersz nazwa="Parser" online={stan.parser.online} opis={opisParsera()} />
          <Wiersz
            nazwa="Baza danych"
            online={stan.baza.online}
            opis={stan.baza.ms !== null ? `odpowiedź ${stan.baza.ms.toLocaleString('pl-PL')} ms` : null}
          />
          <Wiersz nazwa="Magazyn plików" online={!!stan.magazyn.dostepny} opis={opisMagazynu()} />
        </div>
      )}
    </Card>
  );
}
