'use client';

import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

interface ChatSource {
  filename?: string;
  file_id?: number;
  url?: string;
  page?: number;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  error?: boolean;
}

/**
 * Przygotuj tekst odpowiedzi do renderowania Markdown.
 * Skraca "wystające" linie kropek z formularzy (wielokropki pól do wypełnienia),
 * np. "........................................" → "……………" — nie rozpychają dymka.
 */
function normalizeAnswer(text: string): string {
  return text
    // długie serie kropek (6+) — skróć do stałego wielokropka pola formularza
    .replace(/\.{6,}/g, '……………')
    // analogicznie serie podkreśleń
    .replace(/_{6,}/g, '……………');
}

/** Wygeneruj identyfikator sesji czatu (trzymany per karta przeglądarki). */
function getSessionId(): string {
  const key = 'chat_session_id';
  let sid = sessionStorage.getItem(key);
  if (!sid) {
    sid = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem(key, sid);
  }
  return sid;
}

/**
 * Parsuj strumień odpowiedzi n8n Chat Trigger.
 *
 * n8n w trybie streaming wysyła linie JSON, np.:
 *   {"type":"begin"} {"type":"item","content":"..."} {"type":"end"}
 * lub czysty tekst (zależnie od wersji). Parser jest tolerancyjny:
 * - linia JSON z content/text/output/chunk → doklej tekst
 * - obiekt z polem sources → zapisz listę źródeł
 * - nie-JSON → doklej surowy tekst
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

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setStreaming(true);

    const token = localStorage.getItem('auth_token');
    // Unikalny identyfikator pytania — po zakończeniu strumienia pobierzemy
    // pod nim listę źródeł zapisaną w backendzie przez workflow n8n.
    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    const appendText = (t: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + t };
        return next;
      });

    const setSources = (sources: ChatSource[]) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, sources };
        return next;
      });

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: text, session_id: getSessionId(), request_id: requestId }),
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
        // SSE: "data: {...}"
        const payload = trimmed.startsWith('data:') ? trimmed.slice(5).trim() : trimmed;
        if (payload === '[DONE]') return;
        try {
          const obj = JSON.parse(payload);
          // pomiń ramki sterujące begin/end bez treści
          if (obj && (obj.type === 'begin' || obj.type === 'end') && !obj.content) {
            if (Array.isArray(obj.sources)) setSources(obj.sources);
            return;
          }
          extractFromParsed(obj, appendText, setSources);
        } catch {
          appendText(payload);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(processLine);
      }
      if (buffer.trim()) processLine(buffer);

      // Po zakończeniu strumienia pobierz źródła odpowiedzi (zapisane przez n8n)
      try {
        const srcRes = await fetch(`/api/chat/sources/${requestId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (srcRes.ok) {
          const data = await srcRes.json();
          if (Array.isArray(data.sources) && data.sources.length > 0) {
            setSources(data.sources);
          }
        }
      } catch {
        // brak źródeł nie jest błędem krytycznym
      }
    } catch (e: any) {
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
    } finally {
      setStreaming(false);
    }
  };

  const renderSourceLabel = (s: ChatSource, i: number) => s.filename || s.url || `Dokument ${i + 1}`;

  const sourceHref = (s: ChatSource): string | null => {
    if (s.url) return s.url;
    if (s.file_id) return `/api/files/${s.file_id}/download`;
    return null;
  };

  // Otwórz dokument źródłowy z tokenem JWT (zwykły <a href> nie niesie
  // nagłówka Authorization → backend zwróciłby "Not authenticated")
  const openSource = async (s: ChatSource) => {
    if (s.url) {
      window.open(s.url, '_blank', 'noopener,noreferrer');
      return;
    }
    if (!s.file_id) return;
    const token = localStorage.getItem('auth_token');
    try {
      const res = await fetch(`/api/files/${s.file_id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Błąd pobierania (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (e: any) {
      alert(e?.message || 'Nie udało się otworzyć dokumentu.');
    }
  };

  return (
    <div className="flex justify-start h-[calc(100vh-120px)]">
      {/* Panel czatu wyrównany do lewej strony obszaru roboczego */}
      <div className="w-full lg:w-[480px] xl:w-[560px] flex flex-col bg-white rounded-lg shadow border border-gray-200">
        {/* Nagłówek */}
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-gray-800">Chat — baza wiedzy</h1>
            <p className="text-xs text-gray-500">Odpowiedzi na podstawie przetworzonych dokumentów</p>
          </div>
          <button
            onClick={() => { sessionStorage.removeItem('chat_session_id'); setMessages([]); }}
            className="text-xs px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
            title="Rozpocznij nową rozmowę"
          >
            Nowa rozmowa
          </button>
        </div>

        {/* Wiadomości */}
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
                          a: ({ href, children }) => (
                            <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{children}</a>
                          ),
                          table: ({ children }) => <table className="border-collapse text-xs my-2">{children}</table>,
                          th: ({ children }) => <th className="border border-gray-300 px-2 py-1 bg-gray-200">{children}</th>,
                          td: ({ children }) => <td className="border border-gray-300 px-2 py-1">{children}</td>,
                        }}
                      >
                        {normalizeAnswer(m.content)}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    streaming && idx === messages.length - 1 ? '…' : ''
                  )
                ) : (
                  m.content || (streaming && idx === messages.length - 1 ? '…' : '')
                )}

                {/* Źródła pod odpowiedzią */}
                {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-gray-300">
                    <p className="text-xs font-medium text-gray-500 mb-1">Źródła:</p>
                    <ul className="space-y-1">
                      {m.sources.map((s, i) => {
                        const clickable = !!sourceHref(s);
                        return (
                          <li key={i} className="text-xs">
                            {clickable ? (
                              <button
                                onClick={() => openSource(s)}
                                className="text-blue-600 hover:underline text-left"
                              >
                                📄 {renderSourceLabel(s, i)}{s.page ? ` (str. ${s.page})` : ''}
                              </button>
                            ) : (
                              <span className="text-gray-600">📄 {renderSourceLabel(s, i)}{s.page ? ` (str. ${s.page})` : ''}</span>
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

        {/* Pole wpisywania */}
        <div className="p-3 border-t border-gray-200">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              rows={2}
              placeholder="Napisz wiadomość… (Enter — wyślij, Shift+Enter — nowa linia)"
              className="flex-1 resize-none border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={streaming}
            />
            <button
              onClick={sendMessage}
              disabled={streaming || !input.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed self-end"
            >
              {streaming ? '…' : 'Wyślij'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
