/** Kwadratowa plakietka z rozszerzeniem pliku — zamiast emoji.
 *
 * Do wersji 1.5 typ pliku niosło emoji (📄, 📊, …). Wyglądało dobrze wyłącznie
 * na Windowsie: te same znaki rysuje inaczej każdy system, a na Linuksie część
 * z nich w ogóle nie ma glifu. Plakietka z rozszerzeniem wygląda tak samo
 * wszędzie i przy okazji mówi wprost, co to za plik.
 *
 * Kolory pochodzą z makiety 1.5 i są przypisane RODZINIE formatu, nie pojedynczemu
 * rozszerzeniu: .doc, .docx i .odt to dla użytkownika jedno („dokument tekstowy"),
 * więc mają ten sam kolor, a rozróżnia je napis.
 */

const KOLORY: Record<string, string> = {
  pdf: '#d62828',
  doc: '#2f66dc', docx: '#2f66dc', odt: '#2f66dc', rtf: '#2f66dc',
  xls: '#20a25a', xlsx: '#20a25a', ods: '#20a25a', csv: '#20a25a',
  ppt: '#e8843c', pptx: '#e8843c', odp: '#e8843c',
  jpg: '#7258ef', jpeg: '#7258ef', png: '#7258ef', gif: '#7258ef', webp: '#7258ef', tif: '#7258ef', tiff: '#7258ef',
  zip: '#65738a', rar: '#65738a', '7z': '#65738a',
};

const KOLOR_DOMYSLNY = '#8a98ae';

export function rozszerzenie(nazwa: string): string {
  const czysta = (nazwa || '').trim();
  const kropka = czysta.lastIndexOf('.');
  // Bez kropki albo kropka na początku („.gitignore") — to nie jest rozszerzenie.
  if (kropka <= 0 || kropka === czysta.length - 1) return '';
  return czysta.slice(kropka + 1).toLowerCase();
}

interface Props {
  filename: string;
  /** Bok kwadratu w pikselach; napis skaluje się razem z nim. */
  size?: number;
  className?: string;
}

export function FileTypeIcon({ filename, size = 32, className = '' }: Props) {
  const ext = rozszerzenie(filename);
  const kolor = KOLORY[ext] || KOLOR_DOMYSLNY;
  // Rozszerzenia dłuższe niż cztery znaki nie mieszczą się w kwadracie i tak
  // nic nie wnoszą — pokazujemy początek.
  const napis = ext ? ext.slice(0, 4).toUpperCase() : '?';
  // Napis 4-znakowy musi być drobniejszy niż 3-znakowy, inaczej wyjdzie poza pole.
  const wysokoscCzcionki = napis.length >= 4 ? size * 0.26 : size * 0.31;

  return (
    <span
      className={`inline-grid shrink-0 place-items-center rounded-[5px] font-extrabold leading-none text-white ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: kolor,
        fontSize: `${wysokoscCzcionki}px`,
        letterSpacing: napis.length >= 4 ? '-0.02em' : 0,
      }}
      // Ikona powtarza informację z nazwy pliku obok, więc dla czytnika ekranu
      // jest ozdobą — inaczej każda pozycja listy czytałaby się dwa razy.
      aria-hidden="true"
    >
      {napis}
    </span>
  );
}

/** Rozmiar pliku po ludzku. Zero bajtów to prawidłowa odpowiedź, brak danych — nie. */
export function rozmiarPliku(bajty: number | null | undefined): string {
  if (bajty === null || bajty === undefined) return '—';
  if (bajty < 1024) return `${bajty} B`;
  const jednostki = ['kB', 'MB', 'GB', 'TB'];
  let wartosc = bajty / 1024;
  let i = 0;
  while (wartosc >= 1024 && i < jednostki.length - 1) {
    wartosc /= 1024;
    i += 1;
  }
  return `${wartosc.toLocaleString('pl-PL', { maximumFractionDigits: wartosc < 10 ? 1 : 0 })} ${jednostki[i]}`;
}
