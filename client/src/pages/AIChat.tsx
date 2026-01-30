import { useState, useEffect, useRef, useCallback } from 'react';
import { getAccessToken } from '../api/client';
import { aiChat } from '../api/client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

interface Message {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export default function AIChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  async function loadConversations() {
    try {
      const list = await aiChat.listConversations();
      setConversations(list);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      setLoadingConversations(false);
    }
  }

  async function selectConversation(id: string) {
    if (id === activeId) return;
    setActiveId(id);
    setMessages([]);
    setLoadingMessages(true);
    try {
      const detail = await aiChat.getConversation(id);
      setMessages(detail.messages);
    } catch (err) {
      console.error('Failed to load conversation:', err);
    } finally {
      setLoadingMessages(false);
    }
  }

  async function createConversation() {
    try {
      const conv = await aiChat.createConversation();
      setConversations((prev) => [conv, ...prev]);
      setActiveId(conv.id);
      setMessages([]);
      textareaRef.current?.focus();
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  }

  async function deleteConversation(id: string) {
    try {
      await aiChat.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  }

  async function sendMessage() {
    if (!input.trim() || !activeId || streaming) return;
    const content = input.trim();
    setInput('');

    // Optimistic user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Update conversation title optimistically if it was untitled
    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeId && !c.title
          ? { ...c, title: content.slice(0, 60) + (content.length > 60 ? '...' : ''), updated_at: new Date().toISOString() }
          : c
      )
    );

    // Start streaming
    setStreaming(true);
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', created_at: new Date().toISOString() },
    ]);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const token = getAccessToken();
      const response = await fetch(
        `${API_BASE}/chat/ai/conversations/${activeId}/messages`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ content }),
          signal: abort.signal,
        }
      );

      if (!response.ok || !response.body) {
        throw new Error('Stream request failed');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const payload = trimmed.slice(6);
          if (payload === '[DONE]') continue;
          if (payload.startsWith('[ERROR]')) {
            console.error('Stream error:', payload);
            continue;
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + payload } : m
            )
          );
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      console.error('Streaming failed:', err);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && !m.content
            ? { ...m, content: 'Failed to get response. Please try again.' }
            : m
        )
      );
    } finally {
      setStreaming(false);
      abortRef.current = null;
      // Refresh conversation list to get server-side title updates
      loadConversations();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function formatContent(text: string) {
    // Simple markdown-ish formatting
    const parts = text.split(/(```[\s\S]*?```|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('```') && part.endsWith('```')) {
        const code = part.slice(3, -3).replace(/^\w*\n/, '');
        return (
          <pre key={i} className="my-2 p-3 bg-black/40 border border-white/5 text-sm font-mono overflow-x-auto whitespace-pre-wrap">
            {code}
          </pre>
        );
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={i} className="px-1.5 py-0.5 bg-white/5 text-emerald-400 text-sm font-mono">
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*')) {
        return <em key={i} className="italic">{part.slice(1, -1)}</em>;
      }
      // Handle newlines
      return part.split('\n').map((line, j) => (
        <span key={`${i}-${j}`}>
          {j > 0 && <br />}
          {line}
        </span>
      ));
    });
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-0 -mx-4 sm:-mx-8 lg:-mx-12 -mt-8">
      {/* Left panel — conversation list */}
      <div className="w-64 flex-shrink-0 border-r border-white/10 flex flex-col bg-zinc-950">
        <div className="p-4 border-b border-white/10">
          <button
            onClick={createConversation}
            className="w-full px-3 py-2 text-[10px] tracking-[0.15em] uppercase bg-white text-black hover:bg-zinc-200 transition-colors font-bold"
          >
            + New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loadingConversations ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-2 h-2 bg-white/30 animate-pulse" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="px-4 py-8 text-center text-zinc-600 text-xs">
              No conversations yet
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`group flex items-center gap-2 px-4 py-3 cursor-pointer border-l-2 transition-all ${
                  activeId === conv.id
                    ? 'bg-zinc-800 border-white text-white'
                    : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900 hover:border-zinc-700'
                }`}
                onClick={() => selectConversation(conv.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs truncate">
                    {conv.title || 'New conversation'}
                  </div>
                  <div className="text-[10px] text-zinc-600 mt-0.5">
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteConversation(conv.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-zinc-600 hover:text-red-400 transition-all"
                  title="Delete"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right panel — messages */}
      <div className="flex-1 flex flex-col min-w-0">
        {!activeId ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="w-10 h-10 mx-auto mb-4 border border-white/10 flex items-center justify-center">
                <svg className="w-5 h-5 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-zinc-600 text-xs mb-4">Select a conversation or start a new one</p>
              <button
                onClick={createConversation}
                className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase bg-white text-black hover:bg-zinc-200 transition-colors font-bold"
              >
                + New Chat
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Message thread */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {loadingMessages ? (
                <div className="flex items-center justify-center py-12">
                  <div className="w-2 h-2 bg-white/30 animate-pulse" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex items-center justify-center h-full text-zinc-600 text-xs">
                  Send a message to start the conversation
                </div>
              ) : (
                <div className="max-w-3xl mx-auto space-y-4">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[80%] px-4 py-3 text-sm leading-relaxed ${
                          msg.role === 'user'
                            ? 'bg-white text-black'
                            : 'bg-zinc-800 border border-white/5 text-zinc-300'
                        }`}
                      >
                        {msg.role === 'assistant' ? (
                          <div className="whitespace-pre-wrap">{formatContent(msg.content)}</div>
                        ) : (
                          <div className="whitespace-pre-wrap">{msg.content}</div>
                        )}
                        {msg.role === 'assistant' && streaming && msg.content === '' && (
                          <span className="inline-block w-2 h-4 bg-zinc-500 animate-pulse" />
                        )}
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>

            {/* Input */}
            <div className="border-t border-white/10 p-4">
              <div className="max-w-3xl mx-auto flex gap-3">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type a message..."
                  rows={1}
                  className="flex-1 bg-zinc-900 border border-white/10 px-4 py-3 text-sm text-white placeholder-zinc-600 resize-none focus:outline-none focus:border-white/20 transition-colors"
                  disabled={streaming}
                />
                <button
                  onClick={sendMessage}
                  disabled={!input.trim() || streaming}
                  className="px-5 py-3 bg-white text-black text-[10px] tracking-[0.15em] uppercase font-bold hover:bg-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                >
                  {streaming ? (
                    <div className="w-4 h-4 border-2 border-black/30 border-t-black animate-spin" />
                  ) : (
                    'Send'
                  )}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
