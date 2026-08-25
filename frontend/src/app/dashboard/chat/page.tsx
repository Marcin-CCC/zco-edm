'use client';

import Link from 'next/link';
import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';

import {
  KEY_FIELDS, PozycjaDokumentu, etykietaDokumentu, zHitow,
  type DokumentPozycja,
} from '@/components/pozycja-dokumentu';
import {
  IconChat, IconChevronRight, IconClose, IconDownload, IconPlus, IconSearch,
  IconSend, IconSparkle, IconStop,
} from '@/components/icons';
import { OcenaOdpowiedzi } from '@/components/ocena-odpowiedzi';
import { Button, Card, PageHeader } from '@/components/ui/primitives';
import { docSchemasApi, docSearchApi } from '@/lib/api';
import { pobierzListeXlsx } from '@/lib/eksport-xlsx';
import { ODMOWA_TEKST, ODMOWY, ZNACZNIK_BRAKU } from '@/lib/odmowa';

// Polska odmiana rzeczownika „dokument" po liczbie
function pluralDocs(n: number): string {
  if (n === 1) return 'dokument';
  const last = n % 10;
  const lastTwo = n % 100;
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return 'dokumenty';
  return 'dokumentów';
}

/** „Sprawdzono też N dokumentów, które nie zostały wykorzystane" z poprawną odmianą. */
function sprawdzoneOpis(n: number): string {
  if (n === 1) return 'Sprawdzono też 1 dokument, który nie został wykorzystany.';
  return `Sprawdzono też ${n} ${pluralDocs(n)}, które nie zostały wykorzystane.`;
}


const OP_LABELS: Record<string, string> = {
  eq: '=', contains: 'zawiera', gte: 'od', lte: 'do', gt: 'po', lt: 'przed',
};

/** Opisz rozpoznany filtr po ludzku, np. „typ: Zarządzenie, data od 2023, data do 2023". */
function describeFilter(
  filter: { doc_type?: string | null; filters?: { field: string; op: string; value: string }[] } | undefined,
  typeNames: Record<string, string>
): string {
  if (!filter) return '';
  const parts: string[] = [];
  if (filter.doc_type) parts.push(`typ: ${typeNames[filter.doc_type] || filter.doc_type}`);
  for (const f of filter.filters || []) {
    parts.push(`${f.field} ${OP_LABELS[f.op] || f.op} ${f.value}`);
  }
  return parts.join(', ');
}

// Zrodlo pod odpowiedzia i wynik wyszukiwarki po polach to ta sama rzecz —
// dokument z rejestru pol opisowych. Typ i wyglad mieszkaja w jednym module,
// zeby oba ekrany nie rozjechaly sie przy pierwszej korekcie.
type ChatSource = DokumentPozycja;

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  error?: boolean;
  /** Ustawiane tylko dla odpowiedzi MODELU — one jedne mają migawkę planu wyszukiwania,
   *  więc tylko pod nimi prosimy o ocenę (podsumowania list nie mają czego diagnozować). */
  requestId?: string;
  /** Identyfikator zapisanej wiadomości; bywa go brak, gdy zapis historii się nie powiódł */
  messageId?: number;
  /** Pytanie, na które to jest odpowiedzią — zapisujemy je razem z oceną */
  pytanie?: string;
  /** Odpowiedź typu LISTA (wypis dokumentów) — tylko takie da się wyeksportować
   *  do arkusza, bo tylko one są zestawieniem, a nie odpowiedzią z treści. */
  lista?: boolean;
}

interface ConvSummary {
  id: number;
  title: string;
  updated_at?: string;
}

/**
 * Usuń z odpowiedzi maszynowy znacznik cytowań źródeł „[[ŹRÓDŁA: 1,3]]".
 * Model dodaje go na końcu; parsuje go n8n (Sources Gate), a użytkownik go nie widzi.
 * Regex tnie od znacznika do końca — działa też dla częściowego znacznika w trakcie
 * streamowania (np. „[[ŹRÓDŁA: 1," bez domknięcia).
 */
// Inline znacznik cytowania: „[Źródło 3]", „[[Źródło 3]]", lista „[Źródło 2, 5]"
// Model zapisuje cytowania na kilka sposobów: [Źródło 1], [Źródło 1, 2], a przy
// wyliczeniach powtarza słowo — [Źródło 1, Źródło 2]. Wzorzec obejmuje wszystkie,
// bo nieobsłużony wariant zostaje w treści jako surowy tekst.
// Postać NEUTRALNA „[[3]]" (identyczna w każdym języku odpowiedzi) idzie pierwsza,
// stara „[Źródło 3]" zostaje dla rozmów zapisanych wcześniej. Same cyfry dopuszczamy
// WYŁĄCZNIE w podwójnym nawiasie — inaczej „[2024]" albo „[ISO 9001]" w treści
// dokumentu wyglądałyby jak cytowanie i znikałyby z odpowiedzi.
const INLINE_MARKER_RE =
  /\[\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]\]|\[{1,2}\s*Źród(?:ło|ła)\s*(\d+(?:\s*,\s*(?:Źród(?:ło|ła)\s*)?\d+)*)\s*\]{1,2}/gi;

/** Usuń maszynowy znacznik zbiorczy z końca oraz niedomknięty ogon w trakcie streamowania. */
function stripEndMarker(text: string): string {
  return text
    // stary znacznik zbiorczy na końcu: „[[ŹRÓDŁA: 1,3]]" / „[[ŹRÓDŁA:…"
    .replace(/\s*\[\[\s*(ŹRÓDŁA|ZRODLA)\s*:[\s\S]*$/i, '')
    // częściowy, niedomknięty znacznik w trakcie streamowania (np. „[[Źró") — żeby nic nie migało
    .replace(/\s*\[{1,2}[^\]]*$/, '');
}

/** Tekst modelu bez znaczników cytowań i nadmiarowych spacji, małymi literami. */
function normalizuj(tekst: string): string {
  return stripInlineMarkers(stripEndMarker(tekst)).replace(/\s+/g, ' ').trim().toLowerCase();
}

/** Usuń inline znaczniki „[Źródło N]" (gdy nie da się ich zamienić na odnośniki). */
function stripInlineMarkers(text: string): string {
  return text.replace(new RegExp(`\\s*${INLINE_MARKER_RE.source}`, 'gi'), '');
}

/**
 * Zamień inline znaczniki „[Źródło N]" na klikalne odnośniki.
 *
 * Numery w tekście to indeksy POBRANYCH fragmentów (1..15), a lista pod odpowiedzią
 * zawiera tylko te faktycznie zacytowane — dlatego przenumerowujemy je w kolejności
 * pierwszego wystąpienia (pierwszy → 1, kolejny nowy → 2), co odpowiada kolejności
 * listy źródeł budowanej po stronie n8n.
 *
 * Zwraca null, gdy mapowanie nie jest pewne (model podał numer spoza zakresu) —
 * wtedy wołający po prostu usuwa znaczniki, czyli zachowuje się jak dotąd.
 */
function linkifyMarkers(text: string, sourcesCount: number): string | null {
  if (!sourcesCount) return null;

  // 1) numery w kolejności pierwszego wystąpienia
  const order: string[] = [];
  for (const m of text.matchAll(INLINE_MARKER_RE)) {
    // Grupa 1 = postać neutralna [[3]], grupa 2 = stara [Źródło 3]. Z „1, Źródło 2"
    // bierzemy same liczby — słowo bywa powtórzone przy wyliczeniu.
    for (const num of (m[1] ?? m[2] ?? '').match(/\d+/g) || []) {
      if (!order.includes(num)) order.push(num);
    }
  }
  if (order.length === 0) return null;

  // Wariant podstawowy: lista źródeł jest kompletna i uporządkowana tak, jak numery
  // znaczników ([Źródło 3] = trzecia pozycja listy), więc numer mapujemy wprost.
  const wSkali = order.every((num) => {
    const n = Number(num);
    return Number.isInteger(n) && n >= 1 && n <= sourcesCount;
  });
  // Wariant zgodności ze starszym przepływem, gdzie przychodziły wyłącznie źródła
  // zacytowane: numery mogą być dowolne, ale musi ich być dokładnie tyle co pozycji.
  const display = wSkali
    ? new Map(order.map((num) => [num, Number(num)]))
    : order.length === sourcesCount
      ? new Map(order.map((num, i) => [num, i + 1]))
      : null;
  if (!display) return null;  // rozjazd → nie zgadujemy, znaczniki usuwamy

  // 2) podmiana na odnośniki markdown (obsługiwane przez własny renderer `a`)
  return text.replace(INLINE_MARKER_RE, (_full, neutralne: string, zeSlowem: string) =>
    ((neutralne ?? zeSlowem ?? '').match(/\d+/g) || [])
      .map((num) => {
        const d = display.get(num);
        return d ? `[${d}](#src-${d})` : '';
      })
      .join('')
  );
}

/**
 * Przygotuj tekst odpowiedzi do renderowania Markdown: znaczniki cytowań zamieniamy
 * na odnośniki (gdy się da) albo usuwamy, plus skracamy „wystające" linie kropek.
 */
function renderAnswer(text: string, sources?: ChatSource[]): string {
  // Znacznik braku odpowiedzi nie jest treścią — jest sygnałem. Użytkownik ma zobaczyć
  // zdanie, i to w swoim języku, a nie „[[BRAK]]".
  if (text.trim().toLowerCase() === ZNACZNIK_BRAKU) return ODMOWA_TEKST;
  const base = stripEndMarker(text);
  const linked = sources && sources.length ? linkifyMarkers(base, sources.length) : null;
  return (linked ?? stripInlineMarkers(base))
    .replace(/\.{6,}/g, '……………')
    .replace(/_{6,}/g, '……………');
}

/**
 * Parsuj strumień odpowiedzi n8n. Tolerancyjny: linia JSON z content/text/output
 * → doklej tekst; obiekt z polem sources → zapisz źródła; nie-JSON → surowy tekst.
 */
function extractFromParsed(obj: any, onText: (t: string) => void, onSources: (s: ChatSource[]) => void) {
  if (obj == null) return;
  if (typeof obj === 'string') { onText(obj); return; }
  if (Array.isArray(obj)) { obj.forEach((o) => extractFromParsed(o, onText, onSources)); return; }
  if (Array.isArray(obj.sources)) onSources(obj.sources);
  const text = obj.content ?? obj.text ?? obj.output ?? obj.chunk ?? obj.message;
  if (typeof text === 'string') onText(text);
  else if (text && typeof text === 'object') extractFromParsed(text, onText, onSources);
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  // Trwa parsowanie (dzieli model z czatem) → pokaż komunikat, że odpowiedź chwilę poczeka
  const [parseWait, setParseWait] = useState(false);
  // Router typu pytania: komunikat pokazujemy dopiero po progu, żeby nie migał (~0,4 s)
  const [routingHint, setRoutingHint] = useState(false);
  // Trwa ponowienie pytania bez kontekstu wątku (po zmianie tematu w rozmowie)
  const [bezKontekstu, setBezKontekstu] = useState(false);
  const [typeNames, setTypeNames] = useState<Record<string, string>>({});
  // Prośba o ocenę odpowiedzi — wyłączalna po stronie backendu jedną zmienną,
  // gdyby okazało się, że korzysta z niej znikomy procent użytkowników.
  const [oceny, setOceny] = useState<{ wlaczone: boolean; powody: { kod: string; etykieta: string }[] }>(
    { wlaczone: false, powody: [] },
  );
  // Dokumenty wskazane w ostatniej odpowiedzi. Do nich odnoszą się pytania
  // typu „co jest w tym dokumencie" — bez tego zbioru nie ma do czego.
  const [zbiorRoboczy, setZbiorRoboczy] = useState<ChatSource[]>([]);
  // Które odpowiedzi mają rozwiniętą listę dokumentów sprawdzonych, ale niewykorzystanych
  // (klucz = pozycja wiadomości na liście)
  const [pokazPozostale, setPokazPozostale] = useState<Record<number, boolean>>({});

  // Nazwy typów dokumentów (slug → nazwa) do etykiet na liście wyników
  useEffect(() => {
    docSchemasApi.list(true)
      .then((rows) => setTypeNames(Object.fromEntries(rows.map((s) => [s.slug, s.name]))))
      .catch(() => { /* brak rejestru = pokażemy same nazwy plików */ });
  }, []);
  useEffect(() => {
    fetch('/api/chat/ocena/konfiguracja', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setOceny({ wlaczone: !!d.wlaczone, powody: d.powody || [] }))
      .catch(() => { /* brak konfiguracji = nie pytamy o ocenę */ });
  }, []);
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [currentConvId, setCurrentConvId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Aktywuj pole wpisywania po zakończeniu generowania (i na starcie),
  // żeby użytkownik mógł od razu pisać bez klikania.
  useEffect(() => {
    if (!streaming) inputRef.current?.focus({ preventScroll: true });
  }, [streaming]);

  const stopGenerating = () => abortRef.current?.abort();

  const loadConversations = useCallback(async () => {
    try {
      const res = await fetch('/api/chat/conversations', { headers: authHeaders() });
      if (res.ok) setConversations(await res.json());
    } catch { /* lista rozmów nie jest krytyczna */ }
  }, []);

  useEffect(() => { loadConversations(); }, [loadConversations]);

  const openConversation = async (id: number) => {
    if (streaming) return;
    try {
      const res = await fetch(`/api/chat/conversations/${id}`, { headers: authHeaders() });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const wiadomosci = (data.messages || []).map((m: any) => ({
        role: m.role,
        content: m.content,
        sources: m.sources || undefined,
      }));
      setMessages(wiadomosci);
      // Odtwórz zbiór roboczy z ostatniej odpowiedzi — po powrocie do rozmowy
      // pytanie „a co jest w tym dokumencie" ma nadal do czego się odnosić.
      const ostatniaOdpowiedz = [...wiadomosci].reverse()
        .find((m: ChatMessage) => m.role === 'assistant' && (m.sources?.length || 0) > 0);
      setZbiorRoboczy(ostatniaOdpowiedz?.sources || []);
      setPokazPozostale({});  // rozwinięcia dotyczą pozycji wiadomości — nowa rozmowa, nowy stan
      setCurrentConvId(id);
    } catch {
      alert('Nie udało się wczytać rozmowy.');
    }
  };

  const newConversation = () => {
    if (streaming) return;
    setCurrentConvId(null);
    setMessages([]);
    setZbiorRoboczy([]);
    setPokazPozostale({});
  };

  const deleteConversation = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Usunąć tę rozmowę?')) return;
    try {
      await fetch(`/api/chat/conversations/${id}`, { method: 'DELETE', headers: authHeaders() });
      if (currentConvId === id) newConversation();
      loadConversations();
    } catch { /* ignore */ }
  };

  /**
   * Wyszukanie dokumentów w rejestrze pól opisowych (ta sama ścieżka, co tryb LISTA).
   * Zwraca gotowe podsumowanie i listę dokumentów albo null, gdy nic nie pasuje.
   */
  const szukajWRejestrze = async (pytanie: string) => {
    const listRes = await docSearchApi.nl(pytanie);
    const hits = listRes.hits || [];
    const docs: ChatSource[] = zHitow(hits, typeNames);
    const slug = listRes.filter?.doc_type;
    const typeName = slug ? (typeNames[slug] || slug) : null;
    return {
      listRes,
      docs,
      typeName,
      // Pytanie nie niosło żadnego kryterium — rejestr nie ma czego szukać
      noCriteria: !!listRes.no_criteria,
      summary: `Znalazłem ${hits.length} ${pluralDocs(hits.length)}` +
        (typeName ? ` (typ: ${typeName})` : '') + '.',
    };
  };

  /**
   * Czy CAŁA odpowiedź to odmowa („nie znaleziono informacji"). Liczy się tylko
   * odmowa w czystej postaci — odpowiedź, która przy okazji zawiera to zdanie,
   * nadal jest odpowiedzią.
   */
  const czystaOdmowa = (tekst: string) => ODMOWY.includes(normalizuj(tekst));

  /**
   * Czy tura NIE niesie odpowiedzi — odmowa modelu albo komunikat aplikacji
   * („nie znalazłem dokumentów", „nie wiem, o które dokumenty chodzi"). Takie tury
   * nie są historią: backend ich nie wysyła modelowi, więc ponawianie „na czysto"
   * po nich byłoby powtórzeniem tego samego zapytania.
   */
  const bezOdpowiedzi = (tekst: string) => {
    if (czystaOdmowa(tekst)) return true;
    const t = normalizuj(tekst).replace(/^_+/, '');
    return ['nie znalazłem dokumentów spełniających kryteria',
            'nie wiem, o które dokumenty chodzi',
            'w systemie nie ma rodzaju dokumentów'].some((p) => t.startsWith(p));
  };

  /**
   * Czy to, co dotąd przyszło ze strumienia, może jeszcze okazać się odmową.
   * Dopóki może, wstrzymujemy pokazywanie tekstu — bez tego użytkownik widzi
   * mignięcie „nie znaleziono", które po ponowieniu i tak znika.
   */
  const zapowiadaOdmowe = (tekst: string) => {
    const t = normalizuj(tekst);
    return t.length > 0 && ODMOWY.some((o) => o.startsWith(t));
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setStreaming(true);

    // Czy trwa parsowanie? Jeśli tak, model jest zajęty — pokaż komunikat oczekiwania.
    // (backend wstrzymuje start kolejnego pliku na czas czatu; czekamy tylko na bieżący)
    setParseWait(false);
    fetch('/api/chat/parse-active', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.active) setParseWait(true); })
      .catch(() => { /* komunikat to tylko UX */ });

    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    // Które zapytanie ostatecznie dało odpowiedź — po ponowieniu „na czysto" jest to
    // druga próba, i to jej migawkę planu ma nieść ewentualna ocena użytkownika.
    let uzytyRequestId = requestId;
    let assistantText = '';
    // Sama odpowiedź modelu, BEZ naszej adnotacji doklejanej na początku wiadomości
    // („Poniżej odpowiedź na podstawie treści dokumentów:"). Rozpoznanie odmowy musi
    // patrzeć tylko na to — inaczej adnotacja maskuje odmowę i ponowienie nie rusza.
    let modelText = '';
    let prefiks = '';
    let finalSources: ChatSource[] = [];
    let aborted = false;
    // Czy backend ma z czego zbudować historię tej rozmowy. Odmowy do historii nie
    // wchodzą, więc liczą się tylko tury z prawdziwą odpowiedzią — bez tego
    // ponawianie „na czysto" byłoby powtarzaniem tego samego zapytania.
    const mialHistorie = messages.some(
      (m) => m.role === 'assistant' && !m.error && m.content.trim() && !bezOdpowiedzi(m.content),
    );
    // Czy jest jeszcze w zanadrzu ponowienie „na czysto" (gaśnie po jego uruchomieniu)
    let mozliwePonowienie = mialHistorie;

    const appendText = (t: string) => {
      setParseWait(false); // pierwszy token → model już odpowiada, chowamy komunikat
      modelText += t;
      // Dopóki odpowiedź może okazać się odmową, a mamy czym ponowić — nie pokazujemy
      // jej. Inaczej „nie znaleziono" mignie na ekranie i zniknie po ponowieniu.
      // Zwykła odpowiedź rozjeżdża się z odmową już na pierwszym słowie, więc czeka
      // najwyżej jeden token.
      if (mozliwePonowienie && zapowiadaOdmowe(modelText)) return;
      assistantText = prefiks + modelText;
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], content: assistantText };
        return next;
      });
    };
    const setSources = (sources: ChatSource[]) => {
      finalSources = sources;
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, sources };
        return next;
      });
    };

    try {
      // Nowa rozmowa? Najpierw ją utwórz — tytuł = pierwsze pytanie.
      // Jej id służy jako session_id (klucz pamięci n8n) → ciągłość wątku.
      let convId = currentConvId;
      if (convId == null) {
        const cRes = await fetch('/api/chat/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ title: text }),
        });
        if (cRes.ok) {
          const conv = await cRes.json();
          convId = conv.id;
          setCurrentConvId(convId);
        }
      }

      // ===== USTALENIE ZAKRESU I FORMY ODPOWIEDZI =====
      // Każde pytanie rozstrzygamy w dwóch niezależnych wymiarach:
      //   1. O JAKIE DOKUMENTY chodzi — z kryteriów w pytaniu (rejestr pól), z odniesienia
      //      do poprzedniej odpowiedzi („w tym dokumencie") albo o żadne konkretne.
      //   2. CZEGO OCZEKUJE użytkownik — listy dokumentów (LISTA) czy odpowiedzi z ich
      //      treści (TRESC).
      // Rozpoznanie typu i wyszukanie w rejestrze są niezależne, więc lecą równolegle —
      // rejestr nie wydłuża odpowiedzi.
      const routeTimer = setTimeout(() => setRoutingHint(true), 600);
      const [route, rejestr] = await Promise.all([
        fetch('/api/chat/route', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ message: text }),
        })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        szukajWRejestrze(text).catch(() => null),
      ]);
      clearTimeout(routeTimer);
      setRoutingHint(false);

      const mode = route?.mode === 'LISTA' ? 'LISTA' : 'TRESC';  // awaria → TRESC
      const doPoprzednich = !!route?.refers_to_previous;

      // Zakres: odniesienie do poprzedniej odpowiedzi ma pierwszeństwo przed kryteriami,
      // bo „co jest w tym dokumencie" nie niesie żadnych własnych kryteriów.
      let zakres: ChatSource[] | null = null;
      // Skąd wziął się zakres — przy ponowieniu „na czysto" zakres z POPRZEDNIEJ
      // odpowiedzi trzeba odrzucić razem z historią (inaczej dalej pytamy o stary
      // temat), a zakres z rejestru zostaje: wynika z TEGO pytania.
      let zakresZPoprzednich = false;
      let zakresOdcięty = false;   // ponowienie „na czysto" odrzuciło zakres z poprzedniej tury
      // Wyjątek od pierwszeństwa: gdy pytanie NAZYWA rodzaj dokumentów („a inne wnioski",
      // „jakie jeszcze wnioski są"), samo definiuje swój zakres i poprzednia odpowiedź go
      // nie zastępuje. Czysta anafora („który z nich jest najnowszy") rodzaju nie nazywa —
      // zmierzone: w 6 na 6 takich wypowiedzi rejestr nie rozpoznaje typu dokumentu.
      const rejestrNazywaTyp = !!rejestr?.listRes.filter?.doc_type && rejestr.docs.length > 0;
      if (doPoprzednich && zbiorRoboczy.length > 0 && !rejestrNazywaTyp) {
        zakres = zbiorRoboczy;
        zakresZPoprzednich = true;
      } else if (rejestr && rejestr.docs.length > 0) {
        zakres = rejestr.docs;
      }

      if (mode === 'LISTA') {
        if (zakres) {
          // Etykieta MUSI opisywać to, co widać na liście. Wcześniej zależała od innego
          // warunku niż sam zakres, więc dawało się dostać „Znalazłem 35 dokumentów"
          // nad listą 10 pozycji z poprzedniej odpowiedzi.
          const summary = zakresZPoprzednich
            ? `Dokumenty wskazane w poprzedniej odpowiedzi (${zakres.length}):`
            : (rejestr?.summary ?? `Znalazłem ${zakres.length} ${pluralDocs(zakres.length)}.`);
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              ...next[next.length - 1], content: summary, sources: zakres!, lista: true,
              pytanie: text,
            };
            return next;
          });
          setZbiorRoboczy(zakres);
          if (convId != null) {
            try {
              await fetch(`/api/chat/conversations/${convId}/turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ user_message: text, assistant_message: summary, sources: zakres }),
              });
              loadConversations();
            } catch { /* zapis historii nie jest krytyczny */ }
          }
          return;  // obsłużone — finally posprząta stan
        }

        // Pytanie o listę, ale nie wiadomo o jaką. Nie wypisujemy całej bazy —
        // to udawanie odpowiedzi. Prosimy o doprecyzowanie, ale TYLKO gdy wypowiedź
        // faktycznie jest ogólnikowa („pokaż wszystkie dokumenty"). Gdy nazywa coś
        // konkretnego, a rejestr nie umiał zamienić tego na warunek (np. „polecenie
        // wyjazdu służbowego"), przechodzimy do odpowiedzi z treści — tam odnośnik do
        // dokumentu i tak się znajdzie, a odesłanie z niczym byłoby najgorszym wyjściem.
        if (!rejestr || (rejestr.noCriteria && rejestr.listRes.generic_query !== false)) {
          const prosba =
            'Nie wiem, o które dokumenty chodzi. Doprecyzuj — możesz podać rodzaj ' +
            '(np. zarządzenia, instrukcje), osobę (np. zatwierdzone przez Kowalską), ' +
            'numer albo rok.';
          assistantText = prosba;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], content: prosba };
            return next;
          });
          if (convId != null) {
            try {
              await fetch(`/api/chat/conversations/${convId}/turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ user_message: text, assistant_message: prosba, sources: [] }),
              });
              loadConversations();
            } catch { /* zapis historii nie jest krytyczny */ }
          }
          return;
        }

        // Kryteria były, ale nic im nie odpowiada.
        const desc = describeFilter(rejestr.listRes.filter, typeNames);
        // Twarde zatrzymanie tylko wtedy, gdy WSZYSTKIE warunki są wiarygodne
        // (numer, data, osoba). Dopasowanie frazy opisowej potrafi nie trafić w
        // sformułowanie użyte w dokumencie, więc wtedy pytamy jeszcze o treść.
        const poPolu =
          (rejestr.listRes.filter?.filters?.length || 0) > 0 && !rejestr.listRes.phrase_filter;

        // Warunek na konkretnym polu (osoba, numer, data) jest precyzyjny: skoro rejestr
        // nic nie zwrócił, to takich dokumentów po prostu nie ma. Odpowiadamy wprost i
        // NIE doklejamy odpowiedzi z treści — inaczej model dopasowuje się do fałszywego
        // założenia pytania (nazywa „instrukcjami” zarządzenie, bo tak brzmiało pytanie).
        if (poPolu) {
          const odpowiedz =
            `Nie znalazłem dokumentów spełniających kryteria${desc ? ` (${desc})` : ''}. ` +
            'Jeśli chodziło Ci o treść dokumentów, a nie o ich zestawienie, zapytaj wprost ' +
            'o zagadnienie — np. „co mówią przepisy o pracy zdalnej?".';
          assistantText = odpowiedz;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], content: odpowiedz };
            return next;
          });
          if (convId != null) {
            try {
              await fetch(`/api/chat/conversations/${convId}/turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ user_message: text, assistant_message: odpowiedz, sources: [] }),
              });
              loadConversations();
            } catch { /* zapis historii nie jest krytyczny */ }
          }
          return;
        }

        // Kryterium było zgrubne (sam rodzaj dokumentu) albo nie było go wcale —
        // odpowiadamy z treści dokumentów.
        //
        // BEZ WSTĘPU: odpowiedź z treści ma wyglądać tak samo niezależnie od tego,
        // którędy do niej doszliśmy. Zapowiedź „Poniżej odpowiedź na podstawie treści
        // dokumentów" pojawiała się tylko na tej ścieżce i wyglądała jak niespójność,
        // bo o drodze dojścia użytkownik nic nie wie i wiedzieć nie musi.
        // Wyjątek: nieznany RODZAJ dokumentu to informacja o samym pytaniu (rejestr
        // takiego rodzaju nie zna), a nie zapowiedź odpowiedzi — ta zostaje.
        const notice = rejestr.listRes.unknown_type
          ? `_W systemie nie ma rodzaju dokumentów „${rejestr.listRes.unknown_type}". ` +
            `Rozpoznawane rodzaje: ${(rejestr.listRes.known_types || []).join(', ')}._\n\n`
          : '';
        assistantText = notice;
        prefiks = notice;
        if (notice) {
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], content: notice };
            return next;
          });
        }
      }
      // ===== KONIEC USTALANIA ZAKRESU =====

      // Treść przeszukujemy w obrębie ustalonego zakresu — dzięki temu „co jest
      // w instrukcji zatwierdzonej przez Dynarską" pyta o treść TEGO dokumentu,
      // zamiast przeczesywać całą bazę.
      const zakresIds = (zakres || []).map((d) => d.file_id).filter((v): v is number => !!v);

      /** Jedno zapytanie do modelu ze strumieniowaniem odpowiedzi.
       *  `useHistory=false` = pytanie „na czysto": bez historii wątku i bez zakresu
       *  odziedziczonego po poprzedniej odpowiedzi. */
      const zapytajModel = async (rid: string, useHistory: boolean) => {
        const ids = !useHistory && zakresZPoprzednich ? [] : zakresIds;
        const controller = new AbortController();
        abortRef.current = controller;
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({
            message: text,
            session_id: String(convId ?? rid),
            request_id: rid,
            file_ids: ids.length > 0 ? ids : undefined,
            use_history: useHistory,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err?.detail || `Błąd czatu (${res.status})`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const processLine = (line: string) => {
          const trimmed = line.trim();
          if (!trimmed) return;
          const payload = trimmed.startsWith('data:') ? trimmed.slice(5).trim() : trimmed;
          if (payload === '[DONE]') return;
          try {
            const obj = JSON.parse(payload);
            if (obj && (obj.type === 'begin' || obj.type === 'end') && !obj.content) {
              if (Array.isArray(obj.sources)) setSources(obj.sources);
              return;
            }
            extractFromParsed(obj, appendText, setSources);
          } catch {
            appendText(payload);
          }
        };

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            lines.forEach(processLine);
          }
          if (buffer.trim()) processLine(buffer);
        } catch (streamErr: any) {
          // Przerwanie przez użytkownika — zatrzymaj strumień, zachowaj to co jest
          if (streamErr?.name === 'AbortError') aborted = true;
          else throw streamErr;
        }

        // Źródła odpowiedzi (zapisane przez n8n po zakończeniu strumienia).
        // Przy przerwaniu pomijamy — odpowiedź jest częściowa.
        if (!aborted) try {
          const srcRes = await fetch(`/api/chat/sources/${rid}`, { headers: authHeaders() });
          if (srcRes.ok) {
            const data = await srcRes.json();
            if (Array.isArray(data.sources) && data.sources.length > 0) {
              setSources(data.sources);
            }
          }
        } catch { /* brak źródeł nie jest błędem krytycznym */ }
      };

      await zapytajModel(requestId, true);

      // ZMIANA TEMATU W WĄTKU: gdy cała odpowiedź to odmowa, a w rozmowie była już
      // historia, pytamy JESZCZE RAZ „na czysto" — bez kontekstu wątku. Zmierzone:
      // „wniosek o urlop" po rozmowie o PPK kończy się odmową, choć retrieval jest
      // pełny (15/15 fragmentów nad progiem), a to samo pytanie w świeżym wątku daje
      // pełną odpowiedź. Przewidywanie zmiany tematu z góry odpada — odległość
      // tematyczna nie rozdziela kontynuacji od zmiany (0,38–0,59 wobec 0,27–0,51),
      // więc reagujemy na WYNIK, a nie na przepowiednię. Jedno ponowienie, tylko po
      // odmowie, więc nie może zepsuć odpowiedzi, która się udała.
      if (!aborted && mozliwePonowienie && czystaOdmowa(modelText)) {
        mozliwePonowienie = false;   // druga próba leci już normalnie, bez wstrzymywania
        assistantText = prefiks;
        modelText = '';
        finalSources = [];
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], content: prefiks, sources: undefined };
          return next;
        });
        setBezKontekstu(true);
        zakresOdcięty = zakresZPoprzednich;
        try {
          await zapytajModel(`${requestId}-r`, false);
          uzytyRequestId = `${requestId}-r`;   // ocena ma dotyczyć TEJ próby
        } finally {
          setBezKontekstu(false);
        }
      }

      // Ostateczna treść wiadomości. Ustawiamy ją zawsze — dzięki temu tekst
      // wstrzymany na czas rozpoznawania odmowy na pewno trafi na ekran. Gdy mimo
      // ponowienia zostaje odmowa, zdejmujemy adnotację zapowiadającą odpowiedź:
      // pusta obietnica nad komunikatem o braku informacji tylko myli.
      if (!aborted) {
        assistantText = prefiks && czystaOdmowa(modelText) ? modelText : prefiks + modelText;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: assistantText,
            // Dopiero tutaj odpowiedź jest kompletna i pochodzi od MODELU — tylko takie
            // pytamy o ocenę, bo tylko one mają po stronie backendu migawkę planu.
            requestId: uzytyRequestId,
            pytanie: text,
          };
          return next;
        });
      }

      // Zbiór roboczy na kolejne pytanie: dokumenty użyte w tej odpowiedzi. Gdy pytanie
      // było już zawężone, zostaje zawężenie — inaczej biorą się z odpowiedzi RAG.
      // Po ponowieniu „na czysto" zakres odziedziczony po poprzedniej odpowiedzi już
      // nie obowiązuje: odpowiedź powstała z innych dokumentów i te mają iść dalej.
      const noweZrodla = (zakresOdcięty ? null : zakres) ?? finalSources.filter((s) => !!s.file_id);
      if (noweZrodla.length > 0) setZbiorRoboczy(noweZrodla);

      // Zapisz turę w historii (pytanie + odpowiedź + źródła)
      if (convId != null && assistantText.trim()) {
        try {
          const zapis = await fetch(`/api/chat/conversations/${convId}/turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
              user_message: text,
              // Zapisujemy z inline znacznikami — dzięki temu po ponownym otwarciu
              // rozmowy odnośniki do źródeł nadal się renderują (znacznik zbiorczy
              // i ogon z końca usuwamy, bo są maszynowe).
              assistant_message: stripEndMarker(assistantText),
              sources: finalSources,
            }),
          });
          // Identyfikator zapisanej odpowiedzi wiąże ocenę z historią rozmowy.
          // Jego brak niczego nie blokuje — ocena zapisze się z samą treścią.
          if (zapis.ok) {
            const dane = await zapis.json().catch(() => null);
            if (dane?.assistant_message_id) {
              setMessages((prev) => {
                const next = [...prev];
                const ostatni = next[next.length - 1];
                if (ostatni?.role === 'assistant') {
                  next[next.length - 1] = { ...ostatni, messageId: dane.assistant_message_id };
                }
                return next;
              });
            }
          }
          loadConversations();
        } catch { /* zapis historii nie jest krytyczny dla samej odpowiedzi */ }
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        // Przerwane przez użytkownika w trakcie łączenia — zostaw co jest.
        aborted = true;
      } else {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            // Bez glifu ostrzegawczego: dymek błędu niesie to samo czerwoną ramką
            // i tłem, a znaki unicode w roli ikony wyglądają inaczej na każdym systemie.
            content: last.content || (e?.message || 'Błąd połączenia z czatem.'),
            error: true,
          };
          return next;
        });
      }
    } finally {
      abortRef.current = null;
      setStreaming(false);
      setParseWait(false);
      setRoutingHint(false);
    }
  };

  // Opis do dymka przy cytowaniu: etykieta + STRONA + nazwa pliku. Bez strony dwa
  // fragmenty tego samego dokumentu dawały identyczny dymek (np. „Załącznik 2").
  const sourceTitle = (s: ChatSource, i: number) => {
    const parts = [etykietaDokumentu(s, i)];
    if (s.page) parts.push(`str. ${s.page}`);
    if (s.doc_type_name && s.filename) parts.push(s.filename);
    return parts.join(' · ');
  };

  const sourceHref = (s: ChatSource): string | null => {
    if (s.url) return s.url;
    if (s.file_id) return `/api/files/${s.file_id}/download`;
    return null;
  };

  // Eksport listy do arkusza. Kolumny i ich kolejność ustala rejestr schematów
  // (Administracja → Schematy dokumentów), więc tutaj wysyłamy tylko identyfikatory
  // dokumentów — w kolejności, w jakiej użytkownik widzi je na ekranie.
  const [eksportTrwa, setEksportTrwa] = useState<number | null>(null);

  // Eksport listy do arkusza — wspólny z wyszukiwarką po polach (lib/eksport-xlsx.ts).
  const pobierzXlsx = async (idx: number, zrodla: ChatSource[], pytanie?: string) => {
    const ids = zrodla.map((s) => s.file_id).filter((id): id is number => !!id);
    if (!ids.length) return;
    setEksportTrwa(idx);
    try {
      await pobierzListeXlsx(ids, pytanie);
    } catch (e: any) {
      alert(e?.message || 'Nie udało się pobrać arkusza.');
    } finally {
      setEksportTrwa(null);
    }
  };

  const openSource = async (s: ChatSource) => {
    if (s.url) { window.open(s.url, '_blank', 'noopener,noreferrer'); return; }
    if (!s.file_id) return;
    try {
      const res = await fetch(`/api/files/${s.file_id}/download`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`Błąd pobierania (${res.status})`);
      const blob = await res.blob();
      window.open(URL.createObjectURL(blob), '_blank');
    } catch (e: any) {
      alert(e?.message || 'Nie udało się otworzyć dokumentu.');
    }
  };

  // Podpowiedzi pytań w pustym oknie czatu — WYŁĄCZONE do czasu ustalenia,
  // skąd mają pochodzić. Obecna wersja buduje je z rejestru schematów („Pokaż
  // dokumenty typu Aneks"), co działa w każdym wdrożeniu, ale nie musi być tym,
  // co najlepiej pokazuje możliwości czatu. Zostawiamy gotowy układ za jednym
  // przełącznikiem, żeby powrót był zmianą jednego słowa, a nie pisaniem od nowa.
  const POKAZ_PRZYKLADOWE_PYTANIA = false;
  const przykladowePytania = POKAZ_PRZYKLADOWE_PYTANIA
    ? Object.values(typeNames).slice(0, 3).map((nazwa) => `Pokaż dokumenty typu ${nazwa}`)
    : [];

  return (
    <div className="flex h-[calc(100vh-118px)] min-h-[560px] flex-col">
      <PageHeader
        title="Chat z AI"
        description="Zadawaj pytania do dokumentów i uzyskuj odpowiedzi z cytowaniem źródeł."
      />

      <div className="grid min-h-0 flex-1 gap-[18px] lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)_220px]">
        {/* Historia rozmów */}
        <Card className="hidden min-h-0 flex-col overflow-hidden lg:flex">
          <div className="border-b border-app-line px-[18px] py-4">
            <h2 className="text-[16px] font-bold text-app-text">Historia chatów</h2>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {conversations.length === 0 && (
              <p className="px-[18px] py-6 text-center text-[12px] text-app-muted">Brak zapisanych rozmów.</p>
            )}
            {conversations.map((c) => (
              <div
                key={c.id}
                onClick={() => openConversation(c.id)}
                // Lewa krawędź zamiast niebieskiego wypełnienia: niebieski jest
                // w tym layoucie kolorem AKCJI, nie stanu.
                className={`group flex cursor-pointer items-center gap-2.5 border-l-[3px] px-4 py-3.5 ${
                  currentConvId === c.id
                    ? 'border-l-app-blue bg-[#f5f8ff]'
                    : 'border-l-transparent hover:bg-app-hover'
                }`}
                title={c.title}
              >
                <span className="shrink-0 text-app-muted"><IconChat size={16} /></span>
                {/* Bez pogrubienia: bieżącą rozmowę oznacza już niebieska krawędź
                    i jasne tło, a lista, w której każda pozycja jest wytłuszczona,
                    nie wyróżnia niczego. */}
                <span className="min-w-0 flex-1 truncate text-[13px] text-app-text">{c.title}</span>
                <button
                  onClick={(e) => deleteConversation(c.id, e)}
                  className="shrink-0 text-app-muted opacity-0 transition-opacity hover:text-app-danger focus:opacity-100 group-hover:opacity-100"
                  title="Usuń rozmowę"
                  aria-label={`Usuń rozmowę: ${c.title}`}
                >
                  <IconClose size={14} />
                </button>
              </div>
            ))}
          </div>
        </Card>

        {/* Rozmowa */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-app-line px-[18px] py-4">
            <h2 className="text-[16px] font-bold text-app-text">Chat z bazy wiedzy</h2>
            <Button small onClick={newConversation} disabled={streaming} title="Rozpocznij nowy chat">
              <IconPlus size={15} />
              Nowy chat
            </Button>
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-[22px] py-5">
            {messages.length === 0 && (
              <div className="mx-auto max-w-lg pt-8 text-center">
                <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-[#edf4ff] text-app-blue">
                  <IconChat size={24} />
                </span>
                <p className="text-[14px] font-bold text-app-text">Zadaj pytanie o treść dokumentów</p>
                <p className="mt-1 text-[12px] text-app-muted">
                  Odpowiedź powstaje wyłącznie z dokumentów, do których masz dostęp, i zawiera odsyłacze
                  do miejsc, z których pochodzi.
                </p>
                {przykladowePytania.length > 0 && (
                  <div className="mt-6 border-t border-app-line pt-4 text-left">
                    <b className="text-[12px] text-[#6b7890]">Wypróbuj przykładowe pytania</b>
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {przykladowePytania.map((p) => (
                        <button
                          key={p}
                          onClick={() => { setInput(p); inputRef.current?.focus(); }}
                          className="flex items-center gap-1.5 rounded-full border border-app-line bg-white px-2.5 py-2 text-[11px] text-app-blue hover:bg-[#eef4ff]"
                        >
                          <IconSparkle size={13} />
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {messages.map((m, idx) => (
              <div key={idx} className={m.role === 'user' ? 'flex justify-end' : ''}>
                <div
                  className={`max-w-[88%] rounded-[12px] border px-4 py-3.5 text-[13px] leading-[1.55] ${
                    m.role === 'user'
                      ? 'whitespace-pre-wrap border-app-line bg-[#f4f7ff] text-app-text'
                      : m.error
                      ? 'whitespace-pre-wrap border-[#fecdd3] bg-app-dangerbg text-app-danger'
                      : 'border-app-line bg-white text-app-text shadow-[0_4px_14px_rgba(20,35,60,.04)]'
                  }`}
                >
                  {m.role === 'assistant' && !m.error ? (
                    m.content ? (
                      <div className="chat-markdown">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                            em: ({ children }) => <em className="italic">{children}</em>,
                            ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-5">{children}</ul>,
                            ol: ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 pl-5">{children}</ol>,
                            li: ({ children }) => <li>{children}</li>,
                            h1: ({ children }) => <p className="mb-2 text-base font-bold">{children}</p>,
                            h2: ({ children }) => <p className="mb-2 font-bold">{children}</p>,
                            h3: ({ children }) => <p className="mb-1 font-semibold">{children}</p>,
                            code: ({ children }) => <code className="rounded bg-app-bg px-1 text-xs">{children}</code>,
                            a: ({ href, children }) => {
                              // Odnośnik do cytowanego źródła („[1]" w treści) — otwiera dokument
                              const srcMatch = /^#src-(\d+)$/.exec(href || '');
                              if (srcMatch) {
                                const nr = Number(srcMatch[1]) - 1;
                                const src = m.sources?.[nr];
                                return (
                                  <button
                                    onClick={() => src && openSource(src)}
                                    title={src ? sourceTitle(src, nr) : undefined}
                                    className="mx-0.5 rounded bg-[#eaf1ff] px-1 py-0.5 align-super text-[10px] font-medium leading-none text-[#2455cc] hover:bg-[#dbe7ff]"
                                  >
                                    {children}
                                  </button>
                                );
                              }
                              return (
                                <a href={href} target="_blank" rel="noopener noreferrer" className="text-app-blue hover:underline">{children}</a>
                              );
                            },
                            table: ({ children }) => <table className="my-2 border-collapse text-xs">{children}</table>,
                            th: ({ children }) => <th className="border border-app-line bg-app-bg px-2 py-1">{children}</th>,
                            td: ({ children }) => <td className="border border-app-line px-2 py-1">{children}</td>,
                          }}
                        >
                          {renderAnswer(m.content, m.sources)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      streaming && idx === messages.length - 1 ? (
                        <span className="italic text-app-muted">
                          {parseWait
                            ? 'Trwa przetwarzanie dokumentów — odpowiedź pojawi się za chwilę.'
                            : bezKontekstu
                            ? 'Nowy temat w tej rozmowie — sprawdzam samo pytanie…'
                            : routingHint
                            ? 'Rozpoznaję rodzaj pytania…'
                            : '…'}
                        </span>
                      ) : ''
                    )
                  ) : (
                    m.content || (streaming && idx === messages.length - 1 ? '…' : '')
                  )}

                  {/* Eksport do arkusza — tylko pod odpowiedzią typu LISTA. Odpowiedź
                      z treści nie jest zestawieniem, więc nie ma czego eksportować. */}
                  {m.lista && m.sources && m.sources.some((s) => s.file_id) && (
                    <div className="mt-2.5">
                      <Button small onClick={() => pobierzXlsx(idx, m.sources!, m.pytanie)} disabled={eksportTrwa === idx}>
                        <IconDownload size={15} />
                        {eksportTrwa === idx ? 'Przygotowuję arkusz…' : 'Pobierz tę listę w pliku XLSX'}
                      </Button>
                    </div>
                  )}

                  {m.role === 'assistant' && m.sources && m.sources.length > 0 && (() => {
                    // Domyślnie pokazujemy TYLKO dokumenty przywołane w treści — reszta
                    // (fragmenty, które model dostał, ale z nich nie skorzystał) czeka pod
                    // zwijką. Przy dużym dokumencie kontekst potrafi mieć kilkanaście
                    // fragmentów z tego samego pliku i lista przytłaczała odpowiedź.
                    const pozycje = m.sources!.map((s, i) => ({ s, numer: i + 1 }));
                    const przywolane = pozycje.filter((p) => p.s.cited !== false);
                    const pozostale = pozycje.filter((p) => p.s.cited === false);
                    const otwarte = !!pokazPozostale[idx];

                    return (
                      <div className="mt-4 border-t border-app-line pt-3">
                        {przywolane.length > 0 && (
                          <>
                            {/* Pod odpowiedzią typu LISTA nagłówka nie ma: sama odpowiedź
                                mówi już „znaleziono N dokumentów", a te kafelki są tymi
                                dokumentami, nie przypisami do wywodu. Przy odpowiedzi
                                z treści nagłówek zostaje — tam źródła trzeba nazwać. */}
                            {!m.lista && (
                              <p className="mb-2 text-[12px] text-[#66758c]">
                                {przywolane.length === 1 ? 'Dokument użyty w odpowiedzi' : 'Dokumenty użyte w odpowiedzi'}
                              </p>
                            )}
                            <div className="grid gap-2">
                              {przywolane.map((p) => (
                                <PozycjaDokumentu
                                  key={p.numer}
                                  d={p.s}
                                  numer={p.numer}
                                  otworz={sourceHref(p.s) ? () => openSource(p.s) : undefined}
                                />
                              ))}
                            </div>
                          </>
                        )}

                        {pozostale.length > 0 && (
                          <div className={przywolane.length > 0 ? 'mt-3' : ''}>
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-[12px] text-app-muted">{sprawdzoneOpis(pozostale.length)}</span>
                              <Button
                                small
                                onClick={() => setPokazPozostale((prev) => ({ ...prev, [idx]: !otwarte }))}
                                aria-expanded={otwarte}
                              >
                                {otwarte ? 'Ukryj dokumenty' : 'Pokaż dokumenty'}
                              </Button>
                            </div>
                            {otwarte && (
                              <div className="mt-2.5 grid gap-2">
                                {pozostale.map((p) => (
                                  <PozycjaDokumentu
                                    key={p.numer}
                                    d={p.s}
                                    numer={p.numer}
                                    uzyty={false}
                                    otworz={sourceHref(p.s) ? () => openSource(p.s) : undefined}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Prośba o ocenę — tylko pod kompletną odpowiedzią MODELU (te mają
                      migawkę planu wyszukiwania), nie pod podsumowaniami list ani błędami. */}
                  {oceny.wlaczone && m.role === 'assistant' && !m.error && m.requestId
                    && !(streaming && idx === messages.length - 1) && (
                    <OcenaOdpowiedzi
                      key={m.requestId}
                      requestId={m.requestId}
                      messageId={m.messageId}
                      pytanie={m.pytanie || ''}
                      odpowiedz={m.content}
                      powody={oceny.powody}
                      authHeaders={authHeaders}
                    />
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Pole wiadomości. Ramka jest wyraźna (2 px), bo to jedyne miejsce na
              tym ekranie, w którym się pisze. */}
          <div className="border-t border-app-line p-[18px]">
            <div className="rounded-[12px] border-2 border-app-field bg-white px-3 pb-2.5 pt-3">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
                }}
                rows={2}
                placeholder="Napisz wiadomość…"
                className="w-full resize-none border-0 bg-transparent text-[13px] text-app-text outline-none placeholder:text-app-muted"
                disabled={streaming}
              />
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] text-[#8592a7]">
                  Enter — wyślij wiadomość, Shift+Enter — nowa linia
                </span>
                {streaming ? (
                  <Button variant="danger" small onClick={stopGenerating} title="Przerwij generowanie odpowiedzi">
                    <IconStop size={15} />
                    Zatrzymaj
                  </Button>
                ) : (
                  <Button variant="primary" small onClick={sendMessage} disabled={!input.trim()}>
                    <IconSend size={15} />
                    Wyślij
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Wyszukiwanie po polach ma od layoutu 1.5 własny ekran — tutaj zostaje
            tylko odsyłacz. Czat odpowiada na pytania o TREŚĆ, tamten ekran szuka po
            STRUKTURZE; dwa pola wyszukiwania obok siebie zmuszały użytkownika do
            zgadywania, do którego wpisać pytanie. */}
        <Link
          href="/dashboard/wyszukiwanie"
          className="hidden self-start rounded-card border border-app-line bg-app-card p-[22px] shadow-card transition-colors hover:bg-app-hover xl:block"
        >
          <span className="mb-4 grid h-[46px] w-[46px] place-items-center rounded-full bg-[#edf4ff] text-app-blue">
            <IconSearch size={22} />
          </span>
          <span className="block text-[15px] font-bold text-app-text">Wyszukiwanie</span>
          <span className="mt-2 block text-[12px] leading-[1.5] text-app-muted">
            Zbuduj zapytanie po polach metadanych i przeszukaj dokumenty.
          </span>
          <span className="mt-3.5 block text-[12px] font-bold text-app-blue">Przejdź do wyszukiwania ›</span>
        </Link>
      </div>
    </div>
  );
}
