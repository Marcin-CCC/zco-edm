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

/**
 * Nazwy pól podstawianych w komunikacie — czytane z DRZEWA, nie wyrażeniem
 * regularnym. Wyrażenie brało za pole także nazwę gałęzi liczebnika: w zapisie
 * `{count, plural, one {zapytanie} other {zapytań}}` widziało `{zapytanie}`
 * i zgłaszało nieistniejący rozjazd między językami.
 */
function pola(komunikat, kod) {
  const znalezione = new Set();
  const obejdz = (elementy) => {
    for (const el of elementy || []) {
      // 1 = argument, 2 = liczba, 3 = data, 4 = godzina, 5 = select, 6 = plural
      if ([1, 2, 3, 4, 5, 6].includes(el.type) && typeof el.value === 'string') {
        znalezione.add(el.value);
      }
      if (el.options) {
        for (const opcja of Object.values(el.options)) obejdz(opcja.value);
      }
      if (el.children) obejdz(el.children);   // znaczniki `<b>…</b>`
    }
  };
  obejdz(new IntlMessageFormat(komunikat, kod).ast);
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

    const oczekiwane = pola(wzorzec, BAZOWY);
    const mam = pola(komunikat, kod);
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
