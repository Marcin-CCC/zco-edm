/**
 * Kontrola katalogów tłumaczeń — uruchamiana PRZED każdą budową.
 *
 * Po co osobny krok: błąd w komunikacie ICU (`{count, plural, ...}`) nie psuje
 * budowy. Wywala się dopiero przy renderowaniu ekranu, który tego napisu używa —
 * czyli u użytkownika, i tylko w jednym języku. Tutaj kosztuje ułamek sekundy.
 *
 * Sprawdzamy trzy rzeczy:
 *  1. każdy komunikat daje się skompilować w SWOIM języku (reguły liczebnika
 *     różnią się: polski ma trzy formy, ukraiński cztery, angielski dwie);
 *  2. tłumaczenie nie używa pola, którego nie ma w polskim oryginale — literówka
 *     w `{count}` zostawiłaby na ekranie surowy nawias;
 *  3. tłumaczenie nie gubi pola, które oryginał podstawia — zniknęłaby liczba.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { IntlMessageFormat } from 'intl-messageformat';

const KATALOGI = join(dirname(fileURLToPath(import.meta.url)), '..', 'messages');
const BAZOWY = 'pl';

/** Spłaszczenie do kluczy z kropkami. */
function splaszcz(obiekt, przedrostek = '') {
  const wynik = {};
  for (const [k, v] of Object.entries(obiekt)) {
    const pelny = przedrostek ? `${przedrostek}.${k}` : k;
    if (typeof v === 'string') wynik[pelny] = v;
    else Object.assign(wynik, splaszcz(v, pelny));
  }
  return wynik;
}

/** Nazwy pól podstawianych w komunikacie — bez zaglądania w gałęzie liczebnika. */
function pola(komunikat) {
  const znalezione = new Set();
  for (const m of komunikat.matchAll(/\{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(?:,|\})/g)) {
    znalezione.add(m[1]);
  }
  return znalezione;
}

const pliki = readdirSync(KATALOGI).filter((f) => f.endsWith('.json'));
const wczytaj = (kod) => splaszcz(JSON.parse(readFileSync(join(KATALOGI, `${kod}.json`), 'utf8')));

const bazowe = wczytaj(BAZOWY);
const bledy = [];

for (const plik of pliki) {
  const kod = plik.replace(/\.json$/, '');
  const katalog = wczytaj(kod);

  for (const [klucz, komunikat] of Object.entries(katalog)) {
    try {
      new IntlMessageFormat(komunikat, kod);
    } catch (e) {
      bledy.push(`${kod}:${klucz} — nie kompiluje się: ${e.message}`);
      continue;
    }
    if (kod === BAZOWY) continue;

    const wzorzec = bazowe[klucz];
    if (wzorzec === undefined) continue;      // klucza spoza bazy pilnują testy backendu

    const oczekiwane = pola(wzorzec);
    const mam = pola(komunikat);
    for (const p of mam) {
      if (!oczekiwane.has(p)) bledy.push(`${kod}:${klucz} — pole {${p}} nie istnieje w polskim oryginale`);
    }
    for (const p of oczekiwane) {
      if (!mam.has(p)) bledy.push(`${kod}:${klucz} — brakuje pola {${p}} z oryginału`);
    }
  }
}

if (bledy.length) {
  console.error('Katalogi tłumaczeń — problemy:');
  for (const b of bledy) console.error('  ' + b);
  process.exit(1);
}

console.log(`Katalogi tłumaczeń OK (${pliki.length} języków, ${Object.keys(bazowe).length} napisów).`);
