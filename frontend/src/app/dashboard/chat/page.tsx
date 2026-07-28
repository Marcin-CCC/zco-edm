'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { DocSearchPanel } from '@/components/doc-search-panel';
import { docSchemasApi, docSearchApi } from '@/lib/api';

// Polska odmiana rzeczownika „dokument" po liczbie
function pluralDocs(n: number): string {
  if (n === 1) return 'dokument';
  const last = n % 10;
  const lastTwo = n % 100;
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return 'dokumenty';
  return 'dokumentów';
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
const INLINE_MARKER_RE = /\[{1,2}\s*Źród(?:ło|ła)\s*(\d+(?:\s*,\s*\d+)*)\s*\]{1,2}/gi;

/** Usuń maszynowy znacznik zbiorczy z końca oraz niedomknięty ogon w trakcie streamowania. */
function stripEndMarker(text: string): string {
  return text
    // stary znacznik zbiorczy na końcu: „[[ŹRÓDŁA: 1,3]]" / „[[ŹRÓDŁA:…"
    .replace(/\s*\[\[\s*(ŹRÓDŁA|ZRODLA)\s*:[\s\S]*$/i, '')
    // częściowy, niedomknięty znacznik w trakcie streamowania (np. „[[Źró") — żeby nic nie migało
    .replace(/\s*\[{1,2}[^\]]*$/, '');
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
    for (const num of m[1].split(',').map((s) => s.trim())) {
      if (num && !order.includes(num)) order.push(num);
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
    nums
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
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
  const [typeNames, setTypeNames] = useState<Record<string, string>>({});
  // Dokumenty wskazane w ostatniej odpowiedzi. Do nich odnoszą się pytania
  // typu „co jest w tym dokumencie" — bez tego zbioru nie ma do czego.
  const [zbiorRoboczy, setZbiorRoboczy] = useState<ChatSource[]>([]);

  // Nazwy typów dokumentów (slug → nazwa) do etykiet na liście wyników
  useEffect(() => {
    docSchemasApi.list(true)
      .then((rows) => setTypeNames(Object.fromEntries(rows.map((s) => [s.slug, s.name]))))
      .catch(() => { /* brak rejestru = pokażemy same nazwy plików */ });
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
    let assistantText = '';
    let finalSources: ChatSource[] = [];
    let aborted = false;

    const appendText = (t: string) => {
      setParseWait(false); // pierwszy token → model już odpowiada, chowamy komunikat
      assistantText += t;
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + t };
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
      if (doPoprzednich && zbiorRoboczy.length > 0) {
        zakres = zbiorRoboczy;
      } else if (rejestr && rejestr.docs.length > 0) {
        zakres = rejestr.docs;
      }

      if (mode === 'LISTA') {
        if (zakres) {
          const summary = doPoprzednich && !rejestr?.docs.length
            ? `Dokumenty z poprzedniej odpowiedzi (${zakres.length}):`
            : (rejestr?.summary ?? `Znalazłem ${zakres.length} ${pluralDocs(zakres.length)}.`);
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], content: summary, sources: zakres! };
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
        // to udawanie odpowiedzi. Prosimy o doprecyzowanie.
        if (!rejestr || rejestr.noCriteria) {
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

        // Kryteria były, ale nic im nie odpowiada. Mówimy to wprost, a odpowiedź
        // z treści doklejamy niżej — router bywa omylny i pytanie mogło dotyczyć treści.
        const desc = describeFilter(rejestr.listRes.filter, typeNames);
        const notice = rejestr.listRes.unknown_type
          ? `_W systemie nie ma rodzaju dokumentów „${rejestr.listRes.unknown_type}". ` +
            `Rozpoznawane rodzaje: ${(rejestr.listRes.known_types || []).join(', ')}. ` +
            `Poniżej odpowiedź na podstawie treści dokumentów:_\n\n`
          : `_Nie znalazłem dokumentów spełniających kryteria${desc ? ` (${desc})` : ''}. ` +
            `Poniżej odpowiedź na podstawie treści dokumentów:_\n\n`;
        assistantText = notice;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], content: notice };
          return next;
        });
      }
      // ===== KONIEC USTALANIA ZAKRESU =====

      // Treść przeszukujemy w obrębie ustalonego zakresu — dzięki temu „co jest
      // w instrukcji zatwierdzonej przez Dynarską" pyta o treść TEGO dokumentu,
      // zamiast przeczesywać całą bazę.
      const zakresIds = (zakres || []).map((d) => d.file_id).filter((v): v is number => !!v);

      const controller = new AbortController();
      abortRef.current = controller;
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          message: text,
          session_id: String(convId ?? requestId),
          request_id: requestId,
          file_ids: zakresIds.length > 0 ? zakresIds : undefined,
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
        const srcRes = await fetch(`/api/chat/sources/${requestId}`, { headers: authHeaders() });
        if (srcRes.ok) {
          const data = await srcRes.json();
          if (Array.isArray(data.sources) && data.sources.length > 0) {
            setSources(data.sources);
          }
        }
      } catch { /* brak źródeł nie jest błędem krytycznym */ }

      // Zbiór roboczy na kolejne pytanie: dokumenty użyte w tej odpowiedzi. Gdy pytanie
      // było już zawężone, zostaje zawężenie — inaczej biorą się z odpowiedzi RAG.
      const noweZrodla = zakres ?? finalSources.filter((s) => !!s.file_id);
      if (noweZrodla.length > 0) setZbiorRoboczy(noweZrodla);

      // Zapisz turę w historii (pytanie + odpowiedź + źródła)
      if (convId != null && assistantText.trim()) {
        try {
          await fetch(`/api/chat/conversations/${convId}/turn`, {
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
                      ) : routingHint ? (
                        <span className="text-gray-500 italic">Rozpoznaję rodzaj pytania…</span>
                      ) : '…'
                    ) : ''
                  )
                ) : (
                  m.content || (streaming && idx === messages.length - 1 ? '…' : '')
                )}

                {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-gray-300">
                    <p className="text-xs font-medium text-gray-500 mb-1">
                      Dokumenty wzięte pod uwagę:
                    </p>
                    <ul className="space-y-1">
                      {m.sources.map((s, i) => {
                        const clickable = !!sourceHref(s);
                        // Fragmenty bez znacznika w treści były w kontekście modelu, ale
                        // nie zostały przez niego przywołane — oznaczamy je wyraźnie,
                        // żeby dało się sprawdzić, skąd naprawdę pochodzi odpowiedź.
                        const przywolane = s.cited !== false;
                        return (
                          <li key={i} className={`text-xs${przywolane ? '' : ' opacity-70'}`}>
                            <span className="text-gray-400 mr-1">{i + 1}.</span>
                            {clickable ? (
                              <button onClick={() => openSource(s)} className="text-blue-600 hover:underline text-left">
                                📄 {renderSourceLabel(s, i)}{s.page ? ` (str. ${s.page})` : ''}
                              </button>
                            ) : (
                              <span className="text-gray-600">📄 {renderSourceLabel(s, i)}{s.page ? ` (str. ${s.page})` : ''}</span>
                            )}
                            {!przywolane && (
                              <span className="text-gray-400 ml-1">— sprawdzony, nieprzywołany w odpowiedzi</span>
                            )}
                            {s.doc_type_name && s.filename && (
                              <div className="text-gray-400 pl-4 break-all">{s.filename}</div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
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
