/**
 * Pobieranie listy dokumentów jako arkusza XLSX.
 *
 * Wspólne dla dwóch miejsc, w których powstaje lista: odpowiedzi czatu typu LISTA
 * i wyszukiwarki po polach. Jedna funkcja, bo obie mają zachowywać się identycznie —
 * ta sama nazwa pliku, ta sama obsługa błędu, ten sam sposób zapisu.
 *
 * Kolumny i ich kolejność ustala backend na podstawie rejestru schematów, więc tutaj
 * wysyłamy wyłącznie identyfikatory dokumentów (w kolejności z ekranu) i treść pytania,
 * z której powstaje nazwa pliku.
 */

import { aktywnyJezyk } from '@/i18n/locales';

function authHeaders(): Record<string, string> {
  // `X-UI-Language`: backend podaje klucz komunikatu i tłumaczy go dopiero przy
  // odpowiedzi, więc musi wiedzieć, co widzi osoba po drugiej stronie. Nagłówek
  // idzie z KAŻDYM żądaniem, także tym bez tokenu.
  const token = localStorage.getItem('auth_token');
  const naglowki: Record<string, string> = { 'X-UI-Language': aktywnyJezyk() };
  if (token) naglowki.Authorization = `Bearer ${token}`;
  return naglowki;
}

/**
 * Pobierz arkusz z listą dokumentów. Rzuca wyjątkiem z czytelnym komunikatem —
 * wołający decyduje, jak go pokazać.
 */
export async function pobierzListeXlsx(fileIds: number[], pytanie?: string): Promise<void> {
  if (!fileIds.length) return;

  const res = await fetch('/api/files/eksport-xlsx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ file_ids: fileIds, pytanie: pytanie?.trim() || null }),
  });
  if (!res.ok) throw new Error(`Nie udało się przygotować arkusza (${res.status}).`);

  // Nagłówek niesie dwa warianty nazwy: `filename*` w UTF-8 (z polskimi znakami)
  // i `filename` transliterowany na ASCII, bo nagłówki HTTP kodowane są w latin-1.
  // Bierzemy ładniejszy, gdy jest.
  const naglowek = res.headers.get('content-disposition') || '';
  const utf8 = naglowek.match(/filename\*=UTF-8''([^;]+)/i);
  const zwykla = naglowek.match(/filename="?([^";]+)"?/);
  const nazwa = utf8 ? decodeURIComponent(utf8[1]) : zwykla?.[1] || 'lista-dokumentow.xlsx';

  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = nazwa;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
