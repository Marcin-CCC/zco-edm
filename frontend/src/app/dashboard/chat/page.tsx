'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { DocSearchPanel } from '@/components/doc-search-panel';
import { OcenaOdpowiedzi } from '@/components/ocena-odpowiedzi';
import { docSchemasApi, docSearchApi } from '@/lib/api';

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

// Pole najlepiej identyfikujące dokument na liście (pierwsze pasujące)
const KEY_FIELDS = ['numer_dokumentu', 'numer', 'numer_aneksu', 'numer_zalacznika', 'data'];


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

interface ChatSource {
  filename?: string;
  file_id?: number;
  url?: string;
  page?: number;
  doc_type?: string;
  doc_type_name?: string;
  doc_key?: string;
  // Czy model przywołał ten fragment znacznikiem w treści. Fragmenty bez znacznika
  // też pokazujemy — bez nich nie da się sprawdzić, na czym oparta jest odpowiedź.
  cited?: boolean;
}

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
const INLINE_MARKER_RE =
  /\[{1,2}\s*Źród(?:ło|ła)\s*(\d+(?:\s*,\s*(?:Źród(?:ło|ła)\s*)?\d+)*)\s*\]{1,2}/gi;

/** Usuń maszynowy znacznik zbiorczy z końca oraz niedomknięty ogon w trakcie streamowania. */
function stripEndMarker(text: string): string {
  return text
    // stary znacznik zbiorczy na końcu: „[[ŹRÓDŁA: 1,3]]" / „[[ŹRÓDŁA:…"
    .replace(/\s*\[\[\s*(ŹRÓDŁA|ZRODLA)\s*:[\s\S]*$/i, '')
    // częściowy, niedomknięty znacznik w trakcie streamowania (np. „[[Źró") — żeby nic nie migało
    .replace(/\s*\[{1,2}[^\]]*$/, '');
}

/** Odmowa modelu w jedynej postaci, w jakiej ją zwraca (prompt narzuca dokładne zdanie). */
const ODMOWA_PELNA = 'niestety, nie znaleziono w dokumentach informacji na ten temat.';

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
    // z „1, Źródło 2" bierzemy same liczby — słowo bywa powtórzone przy wyliczeniu
    for (const num of m[1].match(/\d+/g) || []) {
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
  return text.replace(INLINE_MARKER_RE, (_full, nums: string) =>
    (nums.match(/\d+/g) || [])
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
  const [showSearch, setShowSearch] = useState(false);  // boczne okno wyszukiwania po polach
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
    const docs: ChatSource[] = hits.map((h) => {
      const f = h.fields || {};
      const key = KEY_FIELDS.map((k) => f[k]).find((v) => !!v);
      return {
        filename: h.filename,
        file_id: h.id,
        doc_type: h.doc_type || undefined,
        doc_type_name: h.doc_type ? (typeNames[h.doc_type] || h.doc_type) : undefined,
        doc_key: key || undefined,
      };
    });
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
  const czystaOdmowa = (tekst: string) => normalizuj(tekst) === ODMOWA_PELNA;

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
    return t.length > 0 && ODMOWA_PELNA.startsWith(t);
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
            content: last.content || `⚠ ${e?.message || 'Błąd połączenia z czatem.'}`,
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

  // Etykieta źródła: gdy znamy typ dokumentu, pokaż go zamiast samej nazwy pliku
  // (np. „Zarządzenie nr 8/2023"), nazwa pliku ląduje wtedy w drugiej linii.
  const renderSourceLabel = (s: ChatSource, i: number) => {
    if (s.doc_type_name) {
      return s.doc_key ? `${s.doc_type_name} ${s.doc_key}` : s.doc_type_name;
    }
    return s.filename || s.url || `Dokument ${i + 1}`;
  };

  // Opis do dymka przy cytowaniu: etykieta + STRONA + nazwa pliku. Bez strony dwa
  // fragmenty tego samego dokumentu dawały identyczny dymek (np. „Załącznik 2").
  const sourceTitle = (s: ChatSource, i: number) => {
    const parts = [renderSourceLabel(s, i)];
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

  const pobierzXlsx = async (idx: number, zrodla: ChatSource[]) => {
    const ids = zrodla.map((s) => s.file_id).filter((id): id is number => !!id);
    if (!ids.length) return;
    setEksportTrwa(idx);
    try {
      const res = await fetch('/api/files/eksport-xlsx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ file_ids: ids }),
      });
      if (!res.ok) throw new Error(`Nie udało się przygotować arkusza (${res.status}).`);
      // Nazwę nadaje backend (po typie dokumentów). Nagłówek niesie dwa warianty:
      // `filename*` w UTF-8 (z polskimi znakami) i `filename` transliterowany na ASCII,
      // bo nagłówki HTTP są kodowane w latin-1. Bierzemy ładniejszy, gdy jest.
      const naglowek = res.headers.get('content-disposition') || '';
      const utf8 = naglowek.match(/filename\*=UTF-8''([^;]+)/i);
      const dopasowanie = utf8
        ? [null, decodeURIComponent(utf8[1])]
        : naglowek.match(/filename="?([^"]+)"?/);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = dopasowanie?.[1] || 'lista-dokumentow.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
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

  return (
    <div className="flex flex-col h-[calc(100vh-100px)]">
      {/* Nagłówek strony (wzorzec jak Dashboard) */}
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Baza wiedzy</h1>

      <div className="flex gap-4 flex-1 min-h-0">
      {/* Sidebar z listą rozmów */}
      <aside className="hidden md:flex w-80 flex-col bg-white rounded-lg shadow border border-gray-200">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-800">Historia chatów</h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 && (
            <p className="text-xs text-gray-400 text-center mt-4">Brak zapisanych rozmów.</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`group flex items-center justify-between gap-1 px-3 py-2 rounded-md cursor-pointer text-sm ${
                currentConvId === c.id ? 'bg-blue-50 text-blue-800' : 'text-gray-700 hover:bg-gray-100'
              }`}
              title={c.title}
            >
              <span className="truncate flex-1">{c.title}</span>
              <button
                onClick={(e) => deleteConversation(c.id, e)}
                className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-600 shrink-0"
                title="Usuń rozmowę"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Panel czatu */}
      <div className="w-full lg:w-[480px] xl:w-[560px] flex flex-col bg-white rounded-lg shadow border border-gray-200">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">Chat z bazy wiedzy</h2>
          <button
            onClick={newConversation}
            disabled={streaming}
            className="text-sm font-medium text-blue-600 hover:text-blue-800 disabled:opacity-50"
            title="Rozpocznij nowy chat"
          >
            + Nowy chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 text-sm mt-10">
              Zadaj pytanie dotyczące dokumentów w bazie wiedzy.
            </div>
          )}
          {messages.map((m, idx) => (
            <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-lg px-4 py-2 text-sm break-words ${
                  m.role === 'user'
                    ? 'bg-blue-600 text-white whitespace-pre-wrap'
                    : m.error
                    ? 'bg-red-50 text-red-800 border border-red-200 whitespace-pre-wrap'
                    : 'bg-gray-100 text-gray-800'
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
                          ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
                          li: ({ children }) => <li>{children}</li>,
                          h1: ({ children }) => <p className="font-bold text-base mb-2">{children}</p>,
                          h2: ({ children }) => <p className="font-bold mb-2">{children}</p>,
                          h3: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
                          code: ({ children }) => <code className="bg-gray-200 rounded px-1 text-xs">{children}</code>,
                          a: ({ href, children }) => {
                            // Odnośnik do cytowanego źródła („[1]" w treści) — otwiera dokument
                            const srcMatch = /^#src-(\d+)$/.exec(href || '');
                            if (srcMatch) {
                              const idx = Number(srcMatch[1]) - 1;
                              const src = m.sources?.[idx];
                              return (
                                <button
                                  onClick={() => src && openSource(src)}
                                  title={src ? sourceTitle(src, idx) : undefined}
                                  className="align-super text-[10px] leading-none px-1 py-0.5 mx-0.5 rounded bg-blue-100 text-blue-700 hover:bg-blue-200 font-medium"
                                >
                                  {children}
                                </button>
                              );
                            }
                            return (
                              <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{children}</a>
                            );
                          },
                          table: ({ children }) => <table className="border-collapse text-xs my-2">{children}</table>,
                          th: ({ children }) => <th className="border border-gray-300 px-2 py-1 bg-gray-200">{children}</th>,
                          td: ({ children }) => <td className="border border-gray-300 px-2 py-1">{children}</td>,
                        }}
                      >
                        {renderAnswer(m.content, m.sources)}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    streaming && idx === messages.length - 1 ? (
                      parseWait ? (
                        <span className="text-gray-500 italic">
                          ⏳ Trwa przetwarzanie dokumentów — odpowiedź pojawi się za chwilę.
                        </span>
                      ) : bezKontekstu ? (
                        <span className="text-gray-500 italic">
                          Nowy temat w tej rozmowie — sprawdzam samo pytanie…
                        </span>
                      ) : routingHint ? (
                        <span className="text-gray-500 italic">Rozpoznaję rodzaj pytania…</span>
                      ) : '…'
                    ) : ''
                  )
                ) : (
                  m.content || (streaming && idx === messages.length - 1 ? '…' : '')
                )}

                {/* Eksport do arkusza — tylko pod odpowiedzią typu LISTA. Odpowiedź
                    z treści nie jest zestawieniem, więc nie ma czego eksportować. */}
                {m.lista && m.sources && m.sources.some((s) => s.file_id) && (
                  <div className="mt-2">
                    <button
                      onClick={() => pobierzXlsx(idx, m.sources!)}
                      disabled={eksportTrwa === idx}
                      className="text-sm text-blue-600 hover:underline disabled:text-gray-400 disabled:no-underline"
                    >
                      📊 {eksportTrwa === idx ? 'Przygotowuję arkusz…' : 'Pobierz tę listę w pliku xlsx'}
                    </button>
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

                  // Numer musi odpowiadać znacznikowi w treści, więc po ukryciu części
                  // pozycji w numeracji zostają dziury. Dlatego numer nosi tę samą
                  // niebieską plakietkę co odsyłacz w tekście — czyta się ją jak
                  // etykietę odsyłacza, a nie jak kolejność na liście.
                  const wiersz = ({ s, numer }: { s: ChatSource; numer: number }, uzyty: boolean) => (
                    <li key={numer} className="text-xs">
                      <span
                        className={`align-super text-[10px] leading-none px-1 py-0.5 mr-1 rounded font-medium ${
                          uzyty ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'
                        }`}
                      >
                        {numer}
                      </span>
                      {sourceHref(s) ? (
                        <button onClick={() => openSource(s)} className="text-blue-600 hover:underline text-left">
                          📄 {renderSourceLabel(s, numer - 1)}{s.page ? ` (str. ${s.page})` : ''}
                        </button>
                      ) : (
                        <span className="text-gray-600">📄 {renderSourceLabel(s, numer - 1)}{s.page ? ` (str. ${s.page})` : ''}</span>
                      )}
                      {s.doc_type_name && s.filename && (
                        <div className="text-gray-600 pl-5 break-all">{s.filename}</div>
                      )}
                    </li>
                  );

                  return (
                    <div className="mt-3 pt-2 border-t border-gray-300">
                      {przywolane.length > 0 && (
                        <>
                          <p className="text-xs font-medium text-gray-500 mb-1">
                            {przywolane.length === 1 ? 'Dokument użyty w odpowiedzi:' : 'Dokumenty użyte w odpowiedzi:'}
                          </p>
                          <ul className="space-y-1">{przywolane.map((p) => wiersz(p, true))}</ul>
                        </>
                      )}

                      {pozostale.length > 0 && (
                        <div className={przywolane.length > 0 ? 'mt-2' : ''}>
                          <p className="text-xs font-medium text-gray-500">
                            {sprawdzoneOpis(pozostale.length)}{' '}
                            <button
                              onClick={() => setPokazPozostale((prev) => ({ ...prev, [idx]: !otwarte }))}
                              className="text-blue-600 hover:underline font-medium"
                              aria-expanded={otwarte}
                            >
                              {otwarte ? 'Ukryj te dokumenty' : 'Pokaż te dokumenty'}
                            </button>
                          </p>
                          {otwarte && (
                            <ul className="space-y-1 mt-1">{pozostale.map((p) => wiersz(p, false))}</ul>
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

        <div className="p-3 border-t border-gray-200">
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
              }}
              rows={2}
              placeholder="Napisz wiadomość… (Enter — wyślij, Shift+Enter — nowa linia)"
              className="flex-1 resize-none border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
              disabled={streaming}
            />
            {streaming ? (
              <button
                onClick={stopGenerating}
                className="px-4 py-2 bg-red-600 text-white rounded-md text-sm font-medium hover:bg-red-700 self-end"
                title="Przerwij generowanie odpowiedzi"
              >
                ⏹ Zatrzymaj
              </button>
            ) : (
              <button
                onClick={sendMessage}
                disabled={!input.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed self-end"
              >
                Wyślij
              </button>
            )}
          </div>
        </div>
      </div>

      {showSearch ? (
        <DocSearchPanel onClose={() => setShowSearch(false)} />
      ) : (
        // Zwinięta wyszukiwarka — kafelka z samą lupą, na wysokości nagłówków paneli
        <div className="hidden lg:block self-start">
          <button
            onClick={() => setShowSearch(true)}
            title="Wyszukiwarka po polach"
            className="w-14 h-14 flex items-center justify-center bg-white rounded-lg shadow border border-gray-200 text-xl hover:bg-gray-50 transition-colors"
          >
            🔎
          </button>
        </div>
      )}
      </div>
    </div>
  );
}
