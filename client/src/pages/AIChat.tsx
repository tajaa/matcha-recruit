import { useState, useEffect, useRef, useCallback } from 'react';
import { getAccessToken } from '../api/client';
import { aiChat } from '../api/client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

interface Attachment {
  url: string;
  filename: string;
  content_type: string;
  size: number;
}

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
  attachments?: Attachment[];
}

export default function AIChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewUrlsRef = useRef<Map<File, string>>(new Map());

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Abort any in-flight stream on unmount and revoke preview URLs
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      for (const url of previewUrlsRef.current.values()) {
        URL.revokeObjectURL(url);
      }
      previewUrlsRef.current.clear();
    };
  }, []);

  // Revoke preview URLs when files are removed
  useEffect(() => {
    const currentFiles = new Set(pendingFiles);
    for (const [file, url] of previewUrlsRef.current) {
      if (!currentFiles.has(file)) {
        URL.revokeObjectURL(url);
        previewUrlsRef.current.delete(file);
      }
    }
  }, [pendingFiles]);

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
    if (id === activeId || streaming) return;
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

  function handleFilePick() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files;
    if (!selected) return;
    setPendingFiles((prev) => [...prev, ...Array.from(selected)]);
    // Reset input so the same file can be picked again
    e.target.value = '';
  }

  function removePendingFile(index: number) {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function getPreviewUrl(file: File): string {
    let url = previewUrlsRef.current.get(file);
    if (!url) {
      url = URL.createObjectURL(file);
      previewUrlsRef.current.set(file, url);
    }
    return url;
  }

  async function sendMessage() {
    if ((!input.trim() && pendingFiles.length === 0) || !activeId || streaming) return;
    const content = input.trim();
    setInput('');
    const filesToSend = [...pendingFiles];
    setPendingFiles([]);

    // Build optimistic attachments for the user message preview
    const optimisticAttachments: Attachment[] = filesToSend.map((f) => ({
      url: URL.createObjectURL(f),
      filename: f.name,
      content_type: f.type || 'application/octet-stream',
      size: f.size,
    }));

    // Optimistic user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      attachments: optimisticAttachments,
    };
    setMessages((prev) => [...prev, userMsg]);

    // Update conversation title optimistically if it was untitled
    if (content) {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId && !c.title
            ? { ...c, title: content.slice(0, 60) + (content.length > 60 ? '...' : ''), updated_at: new Date().toISOString() }
            : c
        )
      );
    }

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

      // Build FormData
      const formData = new FormData();
      formData.append('content', content);
      for (const file of filesToSend) {
        formData.append('files', file);
      }

      const response = await fetch(
        `${API_BASE}/chat/ai/conversations/${activeId}/messages`,
        {
          method: 'POST',
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: formData,
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
          try {
            const parsed = JSON.parse(payload);
            if (parsed.error) {
              console.error('Stream error:', parsed.error);
              continue;
            }
            if (parsed.t != null) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: m.content + parsed.t } : m
                )
              );
            }
          } catch {
            // Non-JSON payload (legacy fallback)
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
      // Revoke optimistic blob URLs
      for (const att of optimisticAttachments) {
        if (att.url.startsWith('blob:')) {
          URL.revokeObjectURL(att.url);
        }
      }
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

  function isImageType(ct: string) {
    return ct.startsWith('image/');
  }

  function formatFileSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function getAttachmentUrl(url: string): string {
    if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:')) {
      return url;
    }
    return `${API_BASE}${url}`;
  }

  function renderAttachments(attachments: Attachment[]) {
    if (!attachments || attachments.length === 0) return null;
    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {attachments.map((att, i) =>
          isImageType(att.content_type) ? (
            <a key={i} href={getAttachmentUrl(att.url)} target="_blank" rel="noopener noreferrer">
              <img
                src={getAttachmentUrl(att.url)}
                alt={att.filename}
                className="max-w-[200px] max-h-[150px] object-cover border border-white/10"
              />
            </a>
          ) : (
            <a
              key={i}
              href={getAttachmentUrl(att.url)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 bg-black/20 border border-white/10 text-xs text-zinc-400 hover:text-white transition-colors"
            >
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
              <span className="truncate max-w-[150px]">{att.filename}</span>
              <span className="text-zinc-600">{formatFileSize(att.size)}</span>
            </a>
          )
        )}
      </div>
    );
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
                        {msg.attachments && msg.attachments.length > 0 && renderAttachments(msg.attachments)}
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>

            {/* Input */}
            <div className="border-t border-white/10 p-4">
              <div className="max-w-3xl mx-auto">
                {/* Pending files preview */}
                {pendingFiles.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {pendingFiles.map((file, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 px-3 py-1.5 bg-zinc-800 border border-white/10 text-xs text-zinc-300"
                      >
                        {file.type.startsWith('image/') ? (
                          <img
                            src={getPreviewUrl(file)}
                            alt={file.name}
                            className="w-6 h-6 object-cover"
                          />
                        ) : (
                          <svg className="w-3.5 h-3.5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                          </svg>
                        )}
                        <span className="truncate max-w-[120px]">{file.name}</span>
                        <button
                          onClick={() => removePendingFile(i)}
                          className="text-zinc-600 hover:text-red-400 transition-colors"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex gap-3">
                  {/* Hidden file input */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/*,.pdf,.txt,.csv"
                    onChange={handleFileChange}
                    className="hidden"
                  />

                  {/* Attach button */}
                  <button
                    onClick={handleFilePick}
                    disabled={streaming}
                    className="px-3 py-3 border border-white/10 text-zinc-500 hover:text-white hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                    title="Attach file"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                  </button>

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
                    disabled={(!input.trim() && pendingFiles.length === 0) || streaming}
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
            </div>
          </>
        )}
      </div>
    </div>
  );
}
