import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { MWMessage, MWThreadDetail, MWDocumentVersion } from '../types/matcha-work';
import { matchaWork } from '../api/client';

type Tab = 'chat' | 'preview';

function MessageBubble({ msg }: { msg: MWMessage }) {
  const isUser = msg.role === 'user';
  const isSystem = msg.role === 'system';

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-zinc-500 bg-zinc-800 px-3 py-1 rounded-full">
          {msg.content}
        </span>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-matcha-600 flex items-center justify-center mr-2 flex-shrink-0 mt-0.5">
          <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.5l1.196 4.784" />
          </svg>
        </div>
      )}
      <div
        className={`max-w-[75%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-matcha-600 text-white rounded-tr-sm'
            : 'bg-zinc-800 text-zinc-200 rounded-tl-sm border border-zinc-700/50'
        }`}
      >
        {msg.content}
        {msg.version_created && !isUser && (
          <div className="mt-1.5 text-xs opacity-50">
            Updated to v{msg.version_created}
          </div>
        )}
      </div>
    </div>
  );
}

export default function MatchaWorkThread() {
  const { threadId } = useParams<{ threadId: string }>();
  const navigate = useNavigate();

  const [thread, setThread] = useState<MWThreadDetail | null>(null);
  const [messages, setMessages] = useState<MWMessage[]>([]);
  const [versions, setVersions] = useState<MWDocumentVersion[]>([]);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('chat');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [showFinalizeConfirm, setShowFinalizeConfirm] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const loadThread = useCallback(async () => {
    if (!threadId) return;
    try {
      setLoading(true);
      const [threadData, verData] = await Promise.all([
        matchaWork.getThread(threadId),
        matchaWork.getVersions(threadId),
      ]);
      setThread(threadData);
      setMessages(threadData.messages);
      setVersions(verData);
      // Get PDF URL for current version
      if (threadData.version > 0) {
        const pdfData = await matchaWork.getPdf(threadId);
        setPdfUrl(pdfData.pdf_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load thread');
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  useEffect(() => {
    loadThread();
  }, [loadThread]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = async () => {
    if (!input.trim() || !threadId || sending) return;

    const content = input.trim();
    setInput('');
    setSending(true);
    setError(null);

    try {
      const resp = await matchaWork.sendMessage(threadId, content);
      setMessages((prev) => [...prev, resp.user_message, resp.assistant_message]);
      if (thread) {
        setThread((prev) => prev ? { ...prev, current_state: resp.current_state, version: resp.version } : prev);
      }
      if (resp.pdf_url) {
        setPdfUrl(resp.pdf_url);
        setActiveTab('preview');
      }
      // Refresh versions if state changed
      if (resp.pdf_url) {
        const verData = await matchaWork.getVersions(threadId);
        setVersions(verData);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleRevert = async (version: number) => {
    if (!threadId) return;
    try {
      setSending(true);
      const resp = await matchaWork.revert(threadId, version);
      setMessages((prev) => [...prev, resp.user_message, resp.assistant_message]);
      if (thread) {
        setThread((prev) => prev ? { ...prev, current_state: resp.current_state, version: resp.version } : prev);
      }
      if (resp.pdf_url) setPdfUrl(resp.pdf_url);
      const verData = await matchaWork.getVersions(threadId);
      setVersions(verData);
      setShowVersions(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revert');
    } finally {
      setSending(false);
    }
  };

  const handleFinalize = async () => {
    if (!threadId) return;
    try {
      setFinalizing(true);
      const resp = await matchaWork.finalize(threadId);
      setThread((prev) => prev ? { ...prev, status: 'finalized' } : prev);
      if (resp.pdf_url) setPdfUrl(resp.pdf_url);
      setShowFinalizeConfirm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to finalize');
    } finally {
      setFinalizing(false);
    }
  };

  const isFinalized = thread?.status === 'finalized';
  const isArchived = thread?.status === 'archived';
  const inputDisabled = isFinalized || isArchived || sending;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center">
          <p className="text-zinc-400">Thread not found</p>
          <button
            onClick={() => navigate('/app/matcha/work')}
            className="mt-3 text-sm text-matcha-400 hover:text-matcha-300"
          >
            Back to Matcha Work
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/app/matcha/work')}
            className="text-zinc-400 hover:text-zinc-200 transition-colors flex-shrink-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="text-sm font-medium text-zinc-200 truncate">{thread.title}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-zinc-500">v{thread.version}</span>
              {isFinalized && (
                <span className="text-xs bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded">
                  Finalized
                </span>
              )}
              {isArchived && (
                <span className="text-xs bg-zinc-500/20 text-zinc-400 px-1.5 py-0.5 rounded">
                  Archived
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Mobile tabs */}
          <div className="flex md:hidden bg-zinc-800 rounded-lg p-0.5">
            <button
              onClick={() => setActiveTab('chat')}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                activeTab === 'chat'
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Chat
            </button>
            <button
              onClick={() => setActiveTab('preview')}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                activeTab === 'preview'
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Preview
            </button>
          </div>

          {!isFinalized && !isArchived && (
            <button
              onClick={() => setShowFinalizeConfirm(true)}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Finalize
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-red-400 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:text-red-300">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        {/* Chat panel */}
        <div
          className={`flex flex-col flex-1 min-w-0 md:max-w-[50%] border-r border-zinc-800 ${
            activeTab !== 'chat' ? 'hidden md:flex' : 'flex'
          }`}
        >
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-8">
                <div className="w-10 h-10 rounded-full bg-matcha-600/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-matcha-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <p className="text-sm text-zinc-400 font-medium">Start drafting</p>
                <p className="text-xs text-zinc-600 mt-1 max-w-xs">
                  Tell me about the candidate and role. I'll build the offer letter as we chat.
                </p>
              </div>
            ) : (
              messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
            )}
            {sending && (
              <div className="flex justify-start mb-3">
                <div className="w-7 h-7 rounded-full bg-matcha-600 flex items-center justify-center mr-2 flex-shrink-0">
                  <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.5l1.196 4.784" />
                  </svg>
                </div>
                <div className="bg-zinc-800 border border-zinc-700/50 px-4 py-3 rounded-2xl rounded-tl-sm">
                  <div className="flex gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-4 pb-4 pt-2 flex-shrink-0 border-t border-zinc-800/50">
            {(isFinalized || isArchived) ? (
              <div className="text-center py-3 text-xs text-zinc-500">
                This thread is {thread.status} — no further edits.
              </div>
            ) : (
              <div className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={inputDisabled}
                  placeholder="Describe changes or add details..."
                  rows={1}
                  className="flex-1 bg-zinc-800 border border-zinc-700 rounded-xl px-3.5 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 resize-none focus:outline-none focus:border-matcha-500/50 disabled:opacity-50 transition-colors"
                  style={{ minHeight: '42px', maxHeight: '120px' }}
                  onInput={(e) => {
                    const t = e.currentTarget;
                    t.style.height = 'auto';
                    t.style.height = `${Math.min(t.scrollHeight, 120)}px`;
                  }}
                />
                <button
                  onClick={handleSend}
                  disabled={inputDisabled || !input.trim()}
                  className="w-9 h-9 flex items-center justify-center bg-matcha-600 hover:bg-matcha-700 disabled:opacity-40 rounded-xl transition-colors flex-shrink-0"
                >
                  <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* PDF preview panel */}
        <div
          className={`flex flex-col flex-1 min-w-0 ${
            activeTab !== 'preview' ? 'hidden md:flex' : 'flex'
          }`}
        >
          {/* PDF toolbar */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 flex-shrink-0">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowVersions(!showVersions)}
                className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                v{thread.version}
                <svg className={`w-3 h-3 transition-transform ${showVersions ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
            <div className="flex items-center gap-2">
              {pdfUrl && (
                <a
                  href={pdfUrl}
                  download={`${thread.title}.pdf`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download
                </a>
              )}
            </div>
          </div>

          {/* Version list dropdown */}
          {showVersions && (
            <div className="border-b border-zinc-800 bg-zinc-900 max-h-48 overflow-y-auto">
              {versions.length === 0 ? (
                <div className="px-4 py-3 text-xs text-zinc-500">No versions yet</div>
              ) : (
                versions.map((ver) => (
                  <div
                    key={ver.id}
                    className="flex items-center justify-between px-4 py-2 hover:bg-zinc-800/50"
                  >
                    <div>
                      <span className="text-xs font-medium text-zinc-300">v{ver.version}</span>
                      {ver.diff_summary && (
                        <span className="ml-2 text-xs text-zinc-500">{ver.diff_summary}</span>
                      )}
                      <div className="text-xs text-zinc-600 mt-0.5">
                        {new Date(ver.created_at).toLocaleString()}
                      </div>
                    </div>
                    {ver.version !== thread.version && !isFinalized && (
                      <button
                        onClick={() => handleRevert(ver.version)}
                        className="text-xs text-matcha-400 hover:text-matcha-300 transition-colors"
                      >
                        Revert
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* PDF iframe */}
          <div className="flex-1 bg-zinc-900 min-h-0">
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                className="w-full h-full border-0"
                title="Offer Letter Preview"
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center py-8">
                <div className="w-12 h-12 rounded bg-zinc-800 flex items-center justify-center mb-3">
                  <svg className="w-6 h-6 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <p className="text-sm text-zinc-500">
                  Preview will appear here as you add details
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Finalize confirm modal */}
      {showFinalizeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-sm w-full mx-4 shadow-xl">
            <h2 className="text-base font-semibold text-zinc-100 mb-2">Finalize offer letter?</h2>
            <p className="text-sm text-zinc-400 mb-5">
              This will lock the document and generate a final PDF without a watermark. You won't be
              able to make further edits.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowFinalizeConfirm(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-zinc-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleFinalize}
                disabled={finalizing}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {finalizing ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : null}
                Finalize
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
