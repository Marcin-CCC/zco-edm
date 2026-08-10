'use client';

/**
 * Ocena odpowiedzi pod bąbelkiem czatu: dobra / neutralna / zła.
 *
 * Po co: najgroźniejszy błąd tego systemu jest z danych niewidoczny. Odpowiedź bywa
 * płynna, powołuje się na prawdziwy fragment prawdziwego dokumentu i mimo to jest
 * nieprawdziwa, bo fragment pochodzi z dokumentu o czymś innym. Rozstrzygnąć może
 * tylko ten, kto zna prawidłową odpowiedź — stąd pytanie do użytkownika.
 *
 * Przy ocenie negatywnej prosimy o powód jednym kliknięciem. Samo „źle" jest trudne
 * do wykorzystania: nie wiadomo, czy zawiodło wyszukiwanie, model, czy rozumienie
 * pytania. Cztery gotowe odpowiedzi rozstrzygają to od razu, a kliknięcie powodu jest
 * OPCJONALNE — ocena zapisuje się już przy pierwszym kliknięciu, żeby nikt nie utknął
 * w połowie formularza.
 */
import { useEffect, useRef, useState } from 'react';

interface Powod {
  kod: string;
  etykieta: string;
}

interface Props {
  /** Identyfikator zapytania — wiąże ocenę z migawką planu wyszukiwania po stronie backendu */
  requestId?: string;
  /** Identyfikator zapisanej odpowiedzi (może go nie być, gdy zapis historii się nie udał) */
  messageId?: number;
  pytanie: string;
  odpowiedz: string;
  powody: Powod[];
  authHeaders: () => Record<string, string>;
}

const OCENY = [
  { kod: 'dobra', ikona: '👍', opis: 'Odpowiedź pomogła' },
  { kod: 'neutralna', ikona: '😐', opis: 'Częściowo pomogła' },
  { kod: 'zla', ikona: '👎', opis: 'Odpowiedź nie pomogła' },
] as const;

export function OcenaOdpowiedzi({
  requestId, messageId, pytanie, odpowiedz, powody, authHeaders,
}: Props) {
  const [wybrana, setWybrana] = useState<string | null>(null);
  const [powod, setPowod] = useState<string | null>(null);
  const wierszPowodow = useRef<HTMLDivElement>(null);

  // Jeden slot na komunikat, zawsze znikający po 5 sekundach. Wcześniej podpowiedź
  // „możesz zmienić" wisiała BEZ końca — a że dymek jest nad ikonami, na stałe
  // zasłaniała odnośniki do źródeł tuż nad nim.
  // Licznik w kluczu jest po to, żeby powtórzenie tego samego tekstu odnawiało czas:
  // sam string nie zmieniłby stanu, więc efekt by się nie uruchomił, a dymek zniknąłby
  // w chwili wyznaczonej przez pierwsze kliknięcie.
  const [komunikat, setKomunikat] = useState<{ tekst: string; nr: number } | null>(null);
  const licznik = useRef(0);
  const pokazKomunikat = (tekst: string) => {
    licznik.current += 1;
    setKomunikat({ tekst, nr: licznik.current });
  };

  useEffect(() => {
    if (!komunikat) return;
    const t = setTimeout(() => setKomunikat(null), 5000);
    return () => clearTimeout(t);
  }, [komunikat]);

  // Powody pojawiają się na samym dole rozmowy, więc bez przewinięcia użytkownik
  // widzi z nich najwyżej pierwszy i nie wie, że są kolejne. Przy pierwszym renderze
  // wiersza dosuwamy go do widoku — `block: 'end'` wystarcza, bo to ostatni element.
  useEffect(() => {
    if (wybrana === 'zla' && !powod && wierszPowodow.current) {
      wierszPowodow.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [wybrana, powod]);

  const wyslij = async (ocena: string, kodPowodu?: string) => {
    const pierwsza = wybrana === null;
    setWybrana(ocena);
    if (kodPowodu) setPowod(kodPowodu);
    try {
      await fetch('/api/chat/ocena', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          message_id: messageId ?? null,
          request_id: requestId ?? null,
          ocena,
          powod: kodPowodu ?? null,
          pytanie,
          odpowiedz,
        }),
      });
      // Przy ocenie negatywnej BEZ powodu nie dziękujemy jeszcze — pod spodem
      // wychodzą właśnie przyciski powodu i dymek tylko by je przekrzykiwał.
      if (kodPowodu || ocena !== 'zla') {
        pokazKomunikat(pierwsza
          ? 'Dziękujemy — ocenę możesz jeszcze zmienić'
          : 'Zapisano — liczy się ostatni wybór');
      }
    } catch {
      /* ocena to sygnał, nie transakcja — nie zawracamy użytkownikowi głowy błędem */
    }
  };

  // Układ jest KOLUMNOWY, a powody mają własny wiersz. Wcześniej doklejały się do
  // wiersza z ikonami i przy wąskim bąbelku zawijały się po jednym w linii — widoczny
  // był tylko pierwszy, reszta czekała pod krawędzią okna rozmowy.
  // Komunikat wisi w DYMKU nad ikonami, poza przepływem układu — dzięki temu jego
  // wejście nie rozpycha bąbelka i nie przesuwa rozmowy pod kursorem. Cena tego
  // rozwiązania: dymek nachodzi na to, co jest wyżej (listę źródeł), więc MUSI
  // znikać sam.
  return (
    <div className="mt-2 text-xs text-gray-500">
      <div className="relative flex flex-wrap items-center gap-2">
        {komunikat && (
          <span
            role="status"
            className="pointer-events-none absolute bottom-full left-0 mb-1 whitespace-nowrap
                       rounded-md bg-gray-800 px-2 py-1 text-[11px] text-white shadow-sm"
          >
            {komunikat.tekst}
          </span>
        )}
        <span>{wybrana ? 'Twoja ocena:' : 'Jak oceniasz tę odpowiedź?'}</span>
        {OCENY.map((o) => (
          <button
            key={o.kod}
            type="button"
            title={o.opis}
            aria-label={o.opis}
            aria-pressed={wybrana === o.kod}
            onClick={() => wyslij(o.kod)}
            className={`rounded-md border px-2 py-1 text-sm transition ${
              wybrana === o.kod
                ? 'border-gray-400 bg-gray-100 opacity-100'
                : 'border-transparent opacity-50 hover:opacity-100 hover:border-gray-300'
            }`}
          >
            {o.ikona}
          </button>
        ))}
      </div>

      {/* Powód pytamy tylko przy ocenie negatywnej i tylko raz */}
      {wybrana === 'zla' && !powod && powody.length > 0 && (
        <div ref={wierszPowodow} className="mt-1.5 rounded-md bg-gray-50 p-2">
          <span className="mr-1">Co było nie tak?</span>
          <span className="inline-flex flex-wrap gap-1 align-middle">
            {powody.map((p) => (
              <button
                key={p.kod}
                type="button"
                onClick={() => wyslij('zla', p.kod)}
                className="rounded-full border border-gray-300 bg-white px-2 py-0.5 hover:bg-gray-100"
              >
                {p.etykieta}
              </button>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}
