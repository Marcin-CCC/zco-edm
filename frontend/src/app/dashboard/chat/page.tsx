'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
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

interface ConvSummary {
  id: number;
  title: string;
  updated_at?: string;
}

/**
 * Przygotuj tekst odpowiedzi do renderowania Markdown.
 * Skraca "wystające" linie kropek z formularzy (wielokropki pól do wypełnienia).
 */
function normalizeAnswer(text: string): string {
  return text.replace(/\.{6,}/g, '……………').replace(/_{6,}/g, '……………');
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
    if (!streaming) inputRef.current?.focus();
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
      setMessages(
        (data.messages || []).map((m: any) => ({
          role: m.role,
          content: m.content,
          sources: m.sources || undefined,
        }))
      );
      setCurrentConvId(id);
    } catch {
      alert('Nie udało się wczytać rozmowy.');
    }
  };

  const newConversation = () => {
    if (streaming) return;
    setCurrentConvId(null);
    setMessages([]);
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

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setStreaming(true);

    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    let assistantText = '';
    let finalSources: ChatSource[] = [];
    let aborted = false;

    const appendText = (t: string) => {
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

      const controller = new AbortController();
      abortRef.current = controller;
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          message: text,
          session_id: String(convId ?? requestId),
          request_id: requestId,
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

      // Zapisz turę w historii (pytanie + odpowiedź + źródła)
      if (convId != null && assistantText.trim()) {
        try {
          await fetch(`/api/chat/conversations/${convId}/turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
              user_message: text,
              assistant_message: assistantText,
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
    }
  };

  const renderSourceLabel = (s: ChatSource, i: number) => s.filename || s.url || `Dokument ${i + 1}`;
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
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Chat — baza wiedzy</h1>

      <div className="flex gap-4 flex-1 min-h-0">
      {/* Sidebar z listą rozmów */}
      <aside className="hidden md:flex w-80 flex-col bg-white rounded-lg shadow border border-gray-200">
        <div className="p-3 border-b border-gray-200">
          <button
            onClick={newConversation}
            disabled={streaming}
            className="w-full px-3 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            + Nowa rozmowa
          </button>
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
          <p className="text-xs text-gray-500">Odpowiedzi na podstawie przetworzonych dokumentów</p>
          <button
            onClick={newConversation}
            className="md:hidden text-xs px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
            title="Rozpocznij nową rozmowę"
          >
            Nowa rozmowa
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

                {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-gray-300">
                    <p className="text-xs font-medium text-gray-500 mb-1">Źródła:</p>
                    <ul className="space-y-1">
                      {m.sources.map((s, i) => {
                        const clickable = !!sourceHref(s);
                        return (
                          <li key={i} className="text-xs">
                            {clickable ? (
                              <button onClick={() => openSource(s)} className="text-blue-600 hover:underline text-left">
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
      </div>
    </div>
  );
}
