'use client';

/** Znak instancji: ikona i nazwa — jeden komponent dla paska bocznego, ekranu
 * logowania i podglądu w Ustawieniach.
 *
 * Ikonę rysujemy WPROST na tle, bez własnej ramki ani zaokrąglenia. Do wersji
 * 1.5.4 pasek boczny miał zaszyty w CSS niebieski kwadrat z plusem, a wgrana
 * ikona nie pojawiała się w nim wcale — trafiała wyłącznie do karty przeglądarki.
 * Kwadrat pod spodem był przy tym podwójnym kłopotem: nadpisywał kształt logo
 * klienta i kłócił się z logo, które własne tło już ma. Jeśli znak potrzebuje
 * podkładki, niesie ją wgrany plik.
 *
 * Trzy miejsca korzystają z tego samego komponentu, bo podgląd w Ustawieniach,
 * który pokazuje co innego niż pasek boczny, jest gorszy niż brak podglądu.
 */

interface Props {
  /** Ścieżka w `public/` albo data URI z bazy. */
  ikona: string;
  nazwa: string;
  /** Kolor napisu — na ciemnym tle menu i logowania. */
  kolorNazwy: string;
  /** Bok znaku w pikselach. */
  rozmiar?: number;
  /** Wysokość napisu w pikselach. */
  rozmiarNazwy?: number;
  /** Sam znak, bez napisu (zwinięte menu). */
  bezNazwy?: boolean;
  className?: string;
}

export function Logo({
  ikona,
  nazwa,
  kolorNazwy,
  rozmiar = 36,
  rozmiarNazwy = 28,
  bezNazwy = false,
  className = '',
}: Props) {
  return (
    <span className={`inline-flex select-none items-center gap-[10px] ${className}`}>
      {ikona && (
        // next/image odpada: ikona bywa data URI z bazy, a nie plikiem o znanych
        // wymiarach. `object-contain` pilnuje, żeby nieidealnie kwadratowy plik
        // nie został rozciągnięty.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={ikona}
          // Przy zwiniętym menu znak jest jedyną identyfikacją instancji, więc
          // musi się przedstawić czytnikowi ekranu. Obok napisu byłby powtórzeniem.
          alt={bezNazwy ? nazwa : ''}
          className="flex-none object-contain"
          style={{ width: rozmiar, height: rozmiar }}
        />
      )}
      {!bezNazwy && (
        <span
          className="font-extrabold leading-none"
          style={{ color: kolorNazwy, fontSize: rozmiarNazwy }}
        >
          {nazwa}
        </span>
      )}
    </span>
  );
}
