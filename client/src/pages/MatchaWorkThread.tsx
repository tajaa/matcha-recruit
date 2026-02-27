import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import type {
  MWMessage,
  MWThreadDetail,
  MWDocumentState,
  MWDocumentVersion,
  MWTokenUsage,
  MWUsageSummaryResponse,
  MWReviewRequestStatus,
  MWPresentation,
} from '../types/matcha-work';
import type { HandbookListItem } from '../types';
import { ApiRequestError, handbooks, matchaWork, adminPlatformSettings } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LogoUpload } from '../components/matcha-work/LogoUpload';
import HandbookDistributeModal from '../components/HandbookDistributeModal';

type Tab = 'chat' | 'preview';

function toItemList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter((item) => item.length > 0);
  }
  if (typeof value === 'string') {
    return value
      .split(/\n|;/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }
  return [];
}

function WorkbookPreview({ state }: { state: MWDocumentState }) {
  const [activeView, setActiveView] = useState<'workbook' | 'presentation'>('workbook');
  const sections = state.sections || [];
  const presentation = state.presentation;

  const presentationMarkdown = useCallback((deck: MWPresentation): string => {
    const lines: string[] = [];
    lines.push(`# ${deck.title}`);
    if (deck.subtitle) lines.push('', `_${deck.subtitle}_`);
    lines.push('', `Generated: ${new Date(deck.generated_at).toLocaleString()}`);
    deck.slides.forEach((slide, idx) => {
      lines.push('', `## Slide ${idx + 1}: ${slide.title}`);
      (slide.bullets || []).forEach((bullet) => lines.push(`- ${bullet}`));
      if (slide.speaker_notes) {
        lines.push('', `Notes: ${slide.speaker_notes}`);
      }
    });
    return lines.join('\n');
  }, []);

  const handleDownloadPresentation = useCallback(() => {
    if (!presentation) return;
    const markdown = presentationMarkdown(presentation);
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    const safeTitle = (presentation.title || 'presentation').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    anchor.href = url;
    anchor.download = `${safeTitle || 'presentation'}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }, [presentation, presentationMarkdown]);

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-2">
          <div className="inline-flex items-center border border-white/10">
            <button
              onClick={() => setActiveView('workbook')}
              className={`px-2.5 py-1 text-[11px] uppercase tracking-wider transition-colors ${
                activeView === 'workbook'
                  ? 'bg-white/10 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Workbook
            </button>
            <button
              onClick={() => setActiveView('presentation')}
              className={`px-2.5 py-1 text-[11px] uppercase tracking-wider transition-colors border-l border-white/10 ${
                activeView === 'presentation'
                  ? 'bg-white/10 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Presentation
            </button>
          </div>
          {activeView === 'presentation' && presentation && (
            <button
              onClick={handleDownloadPresentation}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] border border-white/10 text-zinc-300 hover:text-zinc-100 hover:border-white/20 uppercase tracking-wider transition-colors"
            >
              Download Slides
            </button>
          )}
        </div>

        {activeView === 'workbook' ? (
          <>
        <div className="bg-zinc-950 border border-white/10 p-6">
          <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 mb-1">HR Workbook</p>
          <h2 className="text-xl font-bold text-white tracking-tight">
            {state.workbook_title || 'Untitled Workbook'}
          </h2>
          {state.company_name && (
            <p className="text-sm text-zinc-400 mt-1">{state.company_name}</p>
          )}
          {(state.industry || state.objective) && (
            <div className="flex flex-wrap gap-2 mt-4">
              {state.industry && (
                <span className="px-2 py-0.5 border border-white/10 bg-zinc-800 text-zinc-300 text-[10px] uppercase tracking-wider">
                  {state.industry}
                </span>
              )}
              {state.objective && (
                <span className="px-2 py-0.5 border border-matcha-500/20 bg-matcha-500/10 text-matcha-400 text-[10px] uppercase tracking-wider">
                  {state.objective}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {sections.length === 0 ? (
            <div className="border border-white/10 border-dashed p-12 text-center">
              <div className="w-12 h-12 bg-zinc-800 border border-white/10 flex items-center justify-center mx-auto mb-4 text-zinc-600">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-zinc-500 text-sm italic font-mono">
                Waiting for sections to be generated...
              </p>
            </div>
          ) : (
            sections.map((section, idx) => (
              <div key={idx} className="bg-zinc-950 border border-white/10 overflow-hidden">
                <div className="px-5 py-3 border-b border-white/10 bg-zinc-900/30">
                  <h3 className="text-sm font-bold text-zinc-200 tracking-wide uppercase">
                    {section.title}
                  </h3>
                </div>
                <div className="px-5 py-4 prose prose-invert prose-sm max-w-none text-zinc-300 leading-relaxed font-sans">
                  <ReactMarkdown>{section.content}</ReactMarkdown>
                </div>
              </div>
            ))
          )}
        </div>
          </>
        ) : (
          <div className="space-y-4">
            {!presentation || !Array.isArray(presentation.slides) || presentation.slides.length === 0 ? (
              <div className="border border-white/10 border-dashed p-12 text-center">
                <div className="w-12 h-12 bg-zinc-800 border border-white/10 flex items-center justify-center mx-auto mb-4 text-zinc-600">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h8M8 14h5m7 7H4a1 1 0 01-1-1V4a1 1 0 011-1h10.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V20a1 1 0 01-1 1z" />
                  </svg>
                </div>
                <p className="text-zinc-500 text-sm italic font-mono">
                  No presentation generated yet. Use Generate Presentation.
                </p>
              </div>
            ) : (
              <>
                <div className="bg-zinc-950 border border-white/10 p-5">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 mb-1">Presentation Deck</p>
                  <h2 className="text-xl font-bold text-white tracking-tight">{presentation.title}</h2>
                  {presentation.subtitle && (
                    <p className="text-sm text-zinc-400 mt-1">{presentation.subtitle}</p>
                  )}
                  <p className="text-xs text-zinc-500 mt-3">
                    {presentation.slide_count} slide{presentation.slide_count === 1 ? '' : 's'} · Generated {new Date(presentation.generated_at).toLocaleString()}
                  </p>
                </div>
                {presentation.slides.map((slide, idx) => (
                  <div key={`${slide.title}-${idx}`} className="bg-zinc-950 border border-white/10 overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/10 bg-zinc-900/30 flex items-center justify-between">
                      <h3 className="text-sm font-bold text-zinc-200 tracking-wide uppercase">{slide.title}</h3>
                      <span className="text-[10px] text-zinc-500">Slide {idx + 1}</span>
                    </div>
                    <div className="px-5 py-4">
                      <ul className="space-y-1.5">
                        {(slide.bullets || []).map((bullet, bulletIdx) => (
                          <li key={`${bullet}-${bulletIdx}`} className="text-sm text-zinc-300 leading-relaxed">
                            • {bullet}
                          </li>
                        ))}
                      </ul>
                      {slide.speaker_notes && (
                        <div className="mt-4 p-3 bg-zinc-900 border border-white/10">
                          <p className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1">Speaker Notes</p>
                          <p className="text-xs text-zinc-400 whitespace-pre-wrap">{slide.speaker_notes}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function parseEmailList(input: string): string[] {
  const matches = input.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || [];
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const raw of matches) {
    const email = raw.trim().toLowerCase();
    if (!email || seen.has(email)) continue;
    seen.add(email);
    normalized.push(email);
  }
  return normalized;
}

function isInsufficientCreditsMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes('insufficient credits') || text.includes('out of credits');
}

function MessageBubble({ msg }: { msg: MWMessage }) {
  const isUser = msg.role === 'user';
  const isSystem = msg.role === 'system';

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-zinc-500 bg-zinc-800 border border-white/10 px-3 py-1">
          {msg.content}
        </span>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && (
        <div className="w-7 h-7 bg-matcha-600 flex items-center justify-center mr-2 flex-shrink-0 mt-0.5">
          <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.5l1.196 4.784" />
          </svg>
        </div>
      )}
      <div
        className={`max-w-[75%] px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-matcha-600 text-white'
            : 'bg-zinc-800 text-zinc-200 border border-white/10'
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
  const [previewPanelOpen, setPreviewPanelOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [creatingChat, setCreatingChat] = useState(false);
  const [showFinalizeConfirm, setShowFinalizeConfirm] = useState(false);
  const [tokenUsage, setTokenUsage] = useState<(MWTokenUsage & { stage: 'estimate' | 'final' }) | null>(null);
  const [usageSummary, setUsageSummary] = useState<MWUsageSummaryResponse | null>(null);
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [showReviewRequestsModal, setShowReviewRequestsModal] = useState(false);
  const [generatingPresentation, setGeneratingPresentation] = useState(false);
  const [sendingReviewRequests, setSendingReviewRequests] = useState(false);
  const [reviewRecipientInput, setReviewRecipientInput] = useState('');
  const [reviewEmailMessage, setReviewEmailMessage] = useState('');
  const [loadingActiveHandbooks, setLoadingActiveHandbooks] = useState(false);
  const [sendingHandbookSignatures, setSendingHandbookSignatures] = useState(false);
  const [showHandbookSelectorModal, setShowHandbookSelectorModal] = useState(false);
  const [showHandbookDistributeModal, setShowHandbookDistributeModal] = useState(false);
  const [activeHandbooks, setActiveHandbooks] = useState<HandbookListItem[]>([]);
  const [selectedHandbook, setSelectedHandbook] = useState<{ id: string; title: string } | null>(null);

  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [matchaWorkModelMode, setMatchaWorkModelMode] = useState<'light' | 'heavy'>('light');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const loadThread = useCallback(async () => {
    if (!threadId) return;
    try {
      setLoading(true);
      setTokenUsage(null);
      const [threadData, verData, usageData, billingData] = await Promise.all([
        matchaWork.getThread(threadId),
        matchaWork.getVersions(threadId),
        matchaWork.getUsageSummary(30).catch(() => null),
        matchaWork.getBillingBalance().catch(() => null),
      ]);
      setThread(threadData);
      setMessages(threadData.messages);
      setVersions(verData);
      setUsageSummary(usageData);
      setCreditBalance(typeof billingData?.credits_remaining === 'number' ? billingData.credits_remaining : null);
      // Offer-letter threads render a PDF preview.
      if (threadData.task_type === 'offer_letter' && threadData.version > 0) {
        const pdfData = await matchaWork.getPdf(threadId);
        setPdfUrl(pdfData.pdf_url);
      } else {
        setPdfUrl(null);
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
    if (!isAdmin) return;
    adminPlatformSettings.get().then(s => {
      setMatchaWorkModelMode(s.matcha_work_model_mode as 'light' | 'heavy');
    }).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleToggleModel = async () => {
    const next = matchaWorkModelMode === 'light' ? 'heavy' : 'light';
    setMatchaWorkModelMode(next);
    try {
      await adminPlatformSettings.updateMatchaWorkModelMode(next);
    } catch {
      setMatchaWorkModelMode(matchaWorkModelMode);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || !threadId || sending || isOutOfCredits) return;

    const content = input.trim();
    setInput('');
    setSending(true);
    setError(null);
    setTokenUsage(null);

    let streamError: string | null = null;
    let receivedComplete = false;
    let shouldRefreshVersions = false;

    try {
      await matchaWork.sendMessageStream(threadId, content, (event) => {
        if (event.type === 'usage') {
          setTokenUsage(event.data);
          return;
        }

        if (event.type === 'complete') {
          const resp = event.data;
          receivedComplete = true;
          setMessages((prev) => [...prev, resp.user_message, resp.assistant_message]);
          setThread((prev) =>
            prev
              ? { ...prev, current_state: resp.current_state, version: resp.version, ...(resp.task_type ? { task_type: resp.task_type } : {}) }
              : prev
          );
          if (resp.version > 0) {
            shouldRefreshVersions = true;
          }
          const hasWorkbookState =
            Boolean(resp.current_state?.workbook_title) ||
            Boolean(resp.current_state?.company_name) ||
            Boolean(resp.current_state?.objective) ||
            Boolean(resp.current_state?.industry) ||
            (Array.isArray(resp.current_state?.sections) && resp.current_state.sections.length > 0);
          const hasReviewState =
            Boolean(resp.current_state?.review_title) ||
            Boolean(resp.current_state?.review_subject) ||
            Boolean(resp.current_state?.summary) ||
            Boolean(resp.current_state?.context) ||
            Boolean(resp.current_state?.next_steps) ||
            toItemList(resp.current_state?.strengths).length > 0 ||
            toItemList(resp.current_state?.growth_areas).length > 0 ||
            (Array.isArray(resp.current_state?.review_request_statuses) && resp.current_state.review_request_statuses.length > 0);
          const hasOnboardingState = Array.isArray(resp.current_state?.employees) && resp.current_state.employees.length > 0;
          if (resp.pdf_url) {
            setPdfUrl(resp.pdf_url);
            setPreviewPanelOpen(true);
            setActiveTab('preview');
          } else if (hasWorkbookState || hasReviewState || hasOnboardingState) {
            setPreviewPanelOpen(true);
            setActiveTab('preview');
          }
          if (resp.token_usage) {
            setTokenUsage({ ...resp.token_usage, stage: 'final' });
            setUsageSummary((prev) => {
              if (!prev || !resp.token_usage?.model) return prev;

              const promptTokens = resp.token_usage.prompt_tokens ?? 0;
              const completionTokens = resp.token_usage.completion_tokens ?? 0;
              const totalTokens =
                resp.token_usage.total_tokens ?? promptTokens + completionTokens;
              const model = resp.token_usage.model;
              const nowIso = new Date().toISOString();

              let found = false;
              const byModel = prev.by_model.map((row) => {
                if (row.model !== model) return row;
                found = true;
                return {
                  ...row,
                  prompt_tokens: row.prompt_tokens + promptTokens,
                  completion_tokens: row.completion_tokens + completionTokens,
                  total_tokens: row.total_tokens + totalTokens,
                  operation_count: row.operation_count + 1,
                  estimated_operations: row.estimated_operations + (resp.token_usage?.estimated ? 1 : 0),
                  last_seen_at: nowIso,
                };
              });

              if (!found) {
                byModel.push({
                  model,
                  prompt_tokens: promptTokens,
                  completion_tokens: completionTokens,
                  total_tokens: totalTokens,
                  operation_count: 1,
                  estimated_operations: resp.token_usage?.estimated ? 1 : 0,
                  first_seen_at: nowIso,
                  last_seen_at: nowIso,
                });
              }

              byModel.sort((a, b) => b.total_tokens - a.total_tokens);

              return {
                ...prev,
                totals: {
                  prompt_tokens: prev.totals.prompt_tokens + promptTokens,
                  completion_tokens: prev.totals.completion_tokens + completionTokens,
                  total_tokens: prev.totals.total_tokens + totalTokens,
                  operation_count: prev.totals.operation_count + 1,
                  estimated_operations: prev.totals.estimated_operations + (resp.token_usage?.estimated ? 1 : 0),
                },
                by_model: byModel,
              };
            });
          }
          void matchaWork
            .getBillingBalance()
            .then((data) => setCreditBalance(data.credits_remaining))
            .catch(() => {});
          return;
        }

        if (event.type === 'error') {
          const message = event.message || 'Failed to send message';
          if (isInsufficientCreditsMessage(message)) {
            setCreditBalance(0);
            streamError = 'Out of credits. Purchase more credits to continue using Matcha Work.';
          } else {
            streamError = message;
          }
        }
      });

      if (streamError) {
        setError(streamError);
      } else if (!receivedComplete) {
        setError('Failed to send message');
      }

      if (shouldRefreshVersions) {
        const verData = await matchaWork.getVersions(threadId);
        setVersions(verData);
      }
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 402) {
        setCreditBalance(0);
        setError('Out of credits. Purchase more credits to continue using Matcha Work.');
      } else {
        const message = err instanceof Error ? err.message : 'Failed to send message';
        if (isInsufficientCreditsMessage(message)) {
          setCreditBalance(0);
          setError('Out of credits. Purchase more credits to continue using Matcha Work.');
        } else {
          setError(message);
        }
      }
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleLogoUpload = async (file: File) => {
    if (!threadId) return;
    try {
      setError(null);
      const resp = await matchaWork.uploadLogo(threadId, file);
      // Update thread state immediately
      setThread((prev) =>
        prev
          ? {
              ...prev,
              current_state: { ...prev.current_state, company_logo_url: resp.logo_url },
            }
          : prev
      );
      // Refresh PDF if in offer letter mode
      if (isOfferLetter) {
        const pdfData = await matchaWork.getPdf(threadId);
        setPdfUrl(pdfData.pdf_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload logo');
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
        setThread((prev) => prev ? { ...prev, current_state: resp.current_state, version: resp.version, ...(resp.task_type ? { task_type: resp.task_type } : {}) } : prev);
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

  const handleSaveDraft = async () => {
    if (!threadId || savingDraft || isArchived || !isOfferLetter) return;
    try {
      setSavingDraft(true);
      setError(null);
      const resp = await matchaWork.saveDraft(threadId);
      setThread((prev) =>
        prev ? { ...prev, linked_offer_letter_id: resp.linked_offer_letter_id } : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save draft');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleCreateChat = async () => {
    if (creatingChat || !thread) return;
    try {
      setCreatingChat(true);
      setError(null);
      const created = await matchaWork.createThread({ title: 'Untitled Chat' });
      navigate(`/app/matcha/work/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create chat');
    } finally {
      setCreatingChat(false);
    }
  };

  const handleOpenReviewRequestsModal = () => {
    if (!thread) return;
    const existing = (thread.current_state.recipient_emails || []).join(', ');
    setReviewRecipientInput(existing);
    setReviewEmailMessage('');
    setShowReviewRequestsModal(true);
  };

  const handleSendReviewRequests = async () => {
    if (!threadId || sendingReviewRequests) return;

    const recipientEmails = parseEmailList(reviewRecipientInput);
    if (recipientEmails.length === 0) {
      setError('Add at least one valid recipient email');
      return;
    }

    try {
      setSendingReviewRequests(true);
      setError(null);
      await matchaWork.sendReviewRequests(threadId, {
        recipient_emails: recipientEmails,
        custom_message: reviewEmailMessage.trim() || undefined,
      });
      setShowReviewRequestsModal(false);
      await loadThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send review requests');
    } finally {
      setSendingReviewRequests(false);
    }
  };

  const handleOpenHandbookSignatures = async () => {
    if (!threadId || loadingActiveHandbooks || isArchived || !isWorkbook) return;
    try {
      setLoadingActiveHandbooks(true);
      setError(null);
      const allHandbooks = await handbooks.list();
      const active = allHandbooks.filter((row) => row.status === 'active');
      setActiveHandbooks(active);

      if (active.length === 0) {
        setError('No active handbooks found. Publish a handbook first in /handbook.');
        return;
      }

      if (active.length === 1) {
        setSelectedHandbook({ id: active[0].id, title: active[0].title });
        setShowHandbookDistributeModal(true);
        return;
      }

      setShowHandbookSelectorModal(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load active handbooks');
    } finally {
      setLoadingActiveHandbooks(false);
    }
  };

  const handleGeneratePresentation = async () => {
    if (!threadId || generatingPresentation || isArchived || !isWorkbook || isFinalized) return;
    try {
      setGeneratingPresentation(true);
      setError(null);
      await matchaWork.generatePresentation(threadId);
      await loadThread();
      setActiveTab('preview');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate presentation');
    } finally {
      setGeneratingPresentation(false);
    }
  };

  const handleSelectHandbookForSignatures = (handbook: HandbookListItem) => {
    setSelectedHandbook({ id: handbook.id, title: handbook.title });
    setShowHandbookSelectorModal(false);
    setShowHandbookDistributeModal(true);
  };

  const handleSendHandbookSignatures = async (employeeIds?: string[]) => {
    if (!threadId || !selectedHandbook || sendingHandbookSignatures) return;
    try {
      setSendingHandbookSignatures(true);
      setError(null);
      const result = await matchaWork.sendHandbookSignatures(threadId, {
        handbook_id: selectedHandbook.id,
        employee_ids: employeeIds,
      });
      alert(
        `Distributed handbook v${result.handbook_version} to ${result.assigned_count} employees (${result.skipped_existing_count} already assigned).`
      );
      setShowHandbookDistributeModal(false);
      await loadThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send handbook signatures');
    } finally {
      setSendingHandbookSignatures(false);
    }
  };

  const isFinalized = thread?.status === 'finalized';
  const isArchived = thread?.status === 'archived';
  const isOfferLetter = thread?.task_type === 'offer_letter';
  const isReview = thread?.task_type === 'review';
  const isWorkbook = thread?.task_type === 'workbook';
  const isOnboarding = thread?.task_type === 'onboarding';
  const reviewStatuses: MWReviewRequestStatus[] = (thread?.current_state.review_request_statuses || [])
    .filter((row): row is MWReviewRequestStatus => Boolean(row && typeof row === 'object' && row.email));
  const reviewStrengths = toItemList(thread?.current_state.strengths);
  const reviewGrowthAreas = toItemList(thread?.current_state.growth_areas);
  const reviewExpectedResponses = thread?.current_state.review_expected_responses ?? reviewStatuses.length;
  const reviewReceivedResponses = thread?.current_state.review_received_responses ?? reviewStatuses.filter((row) => row.status === 'submitted').length;
  const reviewPendingResponses = thread?.current_state.review_pending_responses ?? Math.max(reviewExpectedResponses - reviewReceivedResponses, 0);
  const isUnscopedChat = thread
    ? thread.version === 0 &&
      messages.length === 0 &&
      Object.keys(thread.current_state || {}).length === 0
    : false;
  const hasOfferLetterPreviewContent = Boolean(pdfUrl);
  const hasWorkbookPreviewContent = Boolean(
    thread?.current_state.workbook_title ||
    thread?.current_state.company_name ||
    thread?.current_state.objective ||
    thread?.current_state.industry ||
    (thread?.current_state.sections && thread.current_state.sections.length > 0) ||
    (thread?.current_state.presentation && thread.current_state.presentation.slides?.length > 0)
  );
  const hasReviewPreviewContent = Boolean(
    thread?.current_state.review_title ||
    thread?.current_state.review_subject ||
    thread?.current_state.summary ||
    thread?.current_state.context ||
    thread?.current_state.next_steps ||
    reviewStrengths.length > 0 ||
    reviewGrowthAreas.length > 0 ||
    reviewStatuses.length > 0
  );
  const hasOnboardingPreviewContent = Boolean(
    thread?.current_state.employees && (thread.current_state.employees as unknown[]).length > 0
  );
  const hasPreviewContent = !isUnscopedChat && (
    hasOfferLetterPreviewContent ||
    hasWorkbookPreviewContent ||
    hasReviewPreviewContent ||
    hasOnboardingPreviewContent
  );
  const isOutOfCredits = creditBalance !== null && creditBalance <= 0;
  const isLowCredits = creditBalance !== null && creditBalance > 0 && creditBalance < 10;
  const inputDisabled = isFinalized || isArchived || sending || isOutOfCredits;
  const formatTokenCount = (value: number | null | undefined) =>
    value == null ? '—' : value.toLocaleString();

  useEffect(() => {
    if (!(previewPanelOpen && hasPreviewContent) && activeTab === 'preview') {
      setActiveTab('chat');
    }
  }, [activeTab, hasPreviewContent, previewPanelOpen]);

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
            onClick={() => navigate('/app/matcha/work/chats')}
            className="mt-3 text-sm text-matcha-400 hover:text-matcha-300"
          >
            Open Chats
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/app/matcha/work/chats')}
            className="text-zinc-500 hover:text-zinc-200 transition-colors flex-shrink-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-medium text-zinc-200 truncate">{thread.title}</h1>
              <span className="text-[10px] text-zinc-600 font-mono border border-white/10 px-1.5 py-0.5 uppercase tracking-wider shrink-0">
                v{thread.version}
              </span>
              <span className="hidden sm:inline text-[10px] text-zinc-500 border border-white/10 px-1.5 py-0.5 uppercase tracking-wider shrink-0">
                {isUnscopedChat || thread.task_type === 'chat' ? 'chat' : thread.task_type === 'review' ? 'review' : thread.task_type === 'workbook' ? 'workbook' : thread.task_type === 'onboarding' ? 'onboarding' : 'offer letter'}
              </span>
              {isFinalized && <span className="text-[10px] text-blue-400 border border-blue-500/20 px-1.5 py-0.5 uppercase tracking-wider shrink-0">Finalized</span>}
              {isArchived && <span className="text-[10px] text-zinc-500 border border-white/10 px-1.5 py-0.5 uppercase tracking-wider shrink-0">Archived</span>}
              {thread.linked_offer_letter_id && <span className="text-[10px] text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 uppercase tracking-wider shrink-0">Draft Saved</span>}
              {tokenUsage && (
                <span className="hidden sm:inline text-[10px] text-zinc-600 font-mono border border-white/10 px-1.5 py-0.5 shrink-0">
                  {tokenUsage.estimated ? '~' : ''}{formatTokenCount(tokenUsage.total_tokens)} tok
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isAdmin && (
            <button
              onClick={handleToggleModel}
              className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono border transition-colors ${
                matchaWorkModelMode === 'heavy'
                  ? 'text-amber-400 border-amber-500/20 hover:border-amber-500/40'
                  : 'text-zinc-500 border-white/10 hover:border-white/20'
              }`}
              title={matchaWorkModelMode === 'heavy' ? 'Switch to light (flash)' : 'Switch to heavy (3.1 pro)'}
            >
              {matchaWorkModelMode === 'heavy' ? '3.1 pro' : 'flash'}
            </button>
          )}

          {/* Mobile preview toggle */}
          {previewPanelOpen && hasPreviewContent && (
            <div className="flex md:hidden border border-white/10">
              <button
                onClick={() => setActiveTab('chat')}
                className={`px-3 py-1 text-xs uppercase tracking-wider transition-colors ${activeTab === 'chat' ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
              >Chat</button>
              <button
                onClick={() => setActiveTab('preview')}
                className={`px-3 py-1 text-xs uppercase tracking-wider transition-colors border-l border-white/10 ${activeTab === 'preview' ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
              >{(isOfferLetter || hasOfferLetterPreviewContent) ? 'Preview' : (isWorkbook || hasWorkbookPreviewContent) ? 'Workbook' : hasOnboardingPreviewContent ? 'Onboarding' : 'Summary'}</button>
            </div>
          )}

          <button
            onClick={handleCreateChat}
            disabled={creatingChat}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v14m7-7H5" />
            </svg>
            {creatingChat ? 'Creating…' : 'New'}
          </button>

          {isOfferLetter && !isArchived && (
            <button
              onClick={handleSaveDraft}
              disabled={savingDraft}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {savingDraft ? 'Saving…' : 'Save Draft'}
            </button>
          )}

          {isReview && !isArchived && (
            <button
              onClick={handleOpenReviewRequestsModal}
              disabled={sendingReviewRequests}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {sendingReviewRequests ? 'Sending…' : 'Send Requests'}
            </button>
          )}

          {isWorkbook && !isArchived && (
            <button
              onClick={handleOpenHandbookSignatures}
              disabled={loadingActiveHandbooks || sendingHandbookSignatures}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {loadingActiveHandbooks ? 'Loading…' : sendingHandbookSignatures ? 'Sending…' : 'Send Signatures'}
            </button>
          )}

          {isWorkbook && !isArchived && !isFinalized && (
            <button
              onClick={handleGeneratePresentation}
              disabled={generatingPresentation}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {generatingPresentation ? 'Generating…' : 'Presentation'}
            </button>
          )}

          {!isFinalized && !isArchived && (
            <button
              onClick={() => setShowFinalizeConfirm(true)}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-200 hover:text-white border border-white/20 hover:border-white/40 transition-all"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

      {isOutOfCredits && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-red-300 text-xs flex items-center justify-between gap-3">
          <span>Out of credits. Purchase more credits to continue using Matcha Work.</span>
          <button
            onClick={() => navigate('/app/matcha/work/billing')}
            className="px-2 py-1 border border-red-500/30 bg-red-600/20 hover:bg-red-600/40 text-red-100 uppercase tracking-wider transition-colors"
          >
            Open Billing
          </button>
        </div>
      )}

      {!isOutOfCredits && isLowCredits && (
        <div className="px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 text-amber-300 text-xs flex items-center justify-between gap-3">
          <span>Low credit warning: {creditBalance} credits remaining.</span>
          <button
            onClick={() => navigate('/app/matcha/work/billing')}
            className="px-2 py-1 border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-100 uppercase tracking-wider transition-colors"
          >
            Buy Credits
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        {/* Chat panel */}
        <div
          className={`flex flex-col flex-1 min-w-0 ${
            previewPanelOpen && hasPreviewContent ? 'md:max-w-[50%] border-r border-white/10' : ''
          } ${
            activeTab !== 'chat' ? 'hidden md:flex' : 'flex'
          }`}
        >
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-8">
                <div className="w-10 h-10 bg-matcha-600/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-matcha-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <p className="text-sm text-zinc-400 font-medium">Start chatting</p>
                <p className="text-xs text-zinc-600 mt-1 max-w-xs">
                  Tell me what you need in natural language.
                </p>
                <div className="mt-3 text-[11px] text-zinc-500 max-w-sm">
                  Default mode: US HR chat. Skills: offer letters, anonymized reviews, HR workbooks, employee onboarding. Ask naturally and Matcha will route commands when supported.
                </div>
                <div className="mt-1 text-[11px] text-zinc-600 max-w-sm">
                  For review workflows, include recipient emails and use Send Requests to distribute links.
                </div>
                {isOfferLetter && !isFinalized && !isArchived && (
                  <LogoUpload
                    onUpload={handleLogoUpload}
                    currentLogoUrl={thread.current_state.company_logo_url}
                  />
                )}
              </div>
            ) : (
              <div className="space-y-1">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} msg={msg} />
                ))}
                {isOfferLetter && !isFinalized && !isArchived && (
                  <div className="mx-4 pb-4">
                    <LogoUpload
                      onUpload={handleLogoUpload}
                      currentLogoUrl={thread.current_state.company_logo_url}
                    />
                  </div>
                )}
              </div>
            )}
            {sending && (
              <div className="flex justify-start mb-3">
                <div className="w-7 h-7 bg-matcha-600 flex items-center justify-center mr-2 flex-shrink-0">
                  <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.5l1.196 4.784" />
                  </svg>
                </div>
                <div className="bg-zinc-800 border border-white/10 px-4 py-3">
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
          <div className="px-4 pb-4 pt-2 flex-shrink-0 border-t border-white/10">
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
                  placeholder={
                    isUnscopedChat
                      ? 'Ask for an offer letter, review, workbook, or onboarding...'
                      : isReview
                      ? 'Add anonymized review details...'
                      : isWorkbook
                      ? 'Describe workbook sections or objective...'
                      : isOnboarding
                      ? 'Add employee details or confirm to create...'
                      : 'Describe changes or add details...'
                  }
                  rows={1}
                  className="flex-1 bg-zinc-900 border border-white/10 px-3.5 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 resize-none focus:outline-none focus:border-white/20 disabled:opacity-50 transition-colors"
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
                  className="w-9 h-9 flex items-center justify-center bg-matcha-600 hover:bg-matcha-700 disabled:opacity-40 transition-colors flex-shrink-0"
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
            !(previewPanelOpen && hasPreviewContent)
              ? 'hidden'
              : activeTab !== 'preview'
              ? 'hidden md:flex'
              : 'flex'
          }`}
        >
          {/* PDF toolbar */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 flex-shrink-0">
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
              {isOfferLetter && pdfUrl && (
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
            <div className="border-b border-white/10 bg-zinc-950 max-h-48 overflow-y-auto">
              {versions.length === 0 ? (
                <div className="px-4 py-3 text-xs text-zinc-500">No versions yet</div>
              ) : (
                versions.map((ver) => (
                  <div
                    key={ver.id}
                    className="flex items-center justify-between px-4 py-2 hover:bg-zinc-800/30 border-b border-white/5"
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
            {(isOfferLetter || hasOfferLetterPreviewContent) ? (
              pdfUrl ? (
                <iframe
                  src={pdfUrl}
                  className="w-full h-full border-0"
                  title="Offer Letter Preview"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center py-8">
                  <div className="w-12 h-12 bg-zinc-800 border border-white/10 flex items-center justify-center mb-3">
                    <svg className="w-6 h-6 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <p className="text-sm text-zinc-500">
                    Preview will appear here as you add details
                  </p>
                </div>
              )
            ) : (isWorkbook || hasWorkbookPreviewContent) ? (
              <WorkbookPreview state={thread.current_state} />
            ) : hasOnboardingPreviewContent ? (
              <div className="h-full overflow-y-auto p-4">
                <div className="max-w-2xl mx-auto bg-zinc-950 border border-white/10 p-4 space-y-3">
                  <p className="text-xs uppercase tracking-wider text-zinc-500">Employee Onboarding</p>
                  <p className="text-sm text-zinc-300">{(thread.current_state.employees as unknown[])?.length || 0} employee(s) queued</p>
                  <p className="text-xs text-zinc-500">Batch status: {thread.current_state.batch_status || 'collecting'}</p>
                </div>
              </div>
            ) : (
              <div className="h-full overflow-y-auto p-4">
                <div className="max-w-2xl mx-auto bg-zinc-950 border border-white/10 p-4 space-y-4">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-500">Anonymous Review</p>
                    <h3 className="text-base font-semibold text-zinc-100 mt-1">
                      {thread.current_state.review_title || thread.current_state.review_subject || 'Untitled Review'}
                    </h3>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs bg-zinc-800 border border-white/10 text-zinc-200 px-2 py-0.5">
                        {thread.current_state.anonymized === false ? 'Not anonymized' : 'Anonymized'}
                      </span>
                      {thread.current_state.overall_rating != null && (
                        <span className="text-xs bg-amber-500/10 border border-amber-500/20 text-amber-300 px-2 py-0.5">
                          Rating: {thread.current_state.overall_rating}/5
                        </span>
                      )}
                    </div>
                  </div>

                  {(thread.current_state.summary || thread.current_state.context) && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Summary</p>
                      <p className="text-sm text-zinc-200 whitespace-pre-wrap">
                        {thread.current_state.summary || thread.current_state.context}
                      </p>
                    </div>
                  )}

                  {reviewStrengths.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Strengths</p>
                      <ul className="space-y-1">
                        {reviewStrengths.map((item, idx) => (
                          <li key={`${item}-${idx}`} className="text-sm text-zinc-200">
                            • {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {reviewGrowthAreas.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Growth Areas</p>
                      <ul className="space-y-1">
                        {reviewGrowthAreas.map((item, idx) => (
                          <li key={`${item}-${idx}`} className="text-sm text-zinc-200">
                            • {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {thread.current_state.next_steps && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Next Steps</p>
                      <p className="text-sm text-zinc-200 whitespace-pre-wrap">
                        {thread.current_state.next_steps}
                      </p>
                    </div>
                  )}

                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Response Tracking</p>
                    <div className="grid grid-cols-3 gap-px bg-white/10 border border-white/10">
                      <div className="bg-zinc-950 p-2">
                        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Expected</p>
                        <p className="text-sm font-mono text-zinc-200 mt-0.5">{reviewExpectedResponses}</p>
                      </div>
                      <div className="bg-zinc-950 p-2">
                        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Received</p>
                        <p className="text-sm font-mono text-emerald-300 mt-0.5">{reviewReceivedResponses}</p>
                      </div>
                      <div className="bg-zinc-950 p-2">
                        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Pending</p>
                        <p className="text-sm font-mono text-amber-300 mt-0.5">{reviewPendingResponses}</p>
                      </div>
                    </div>
                    {reviewStatuses.length > 0 ? (
                      <div className="mt-3 space-y-1.5">
                        {reviewStatuses.map((row) => (
                          <div
                            key={row.email}
                            className="flex items-center justify-between border border-white/10 bg-zinc-950 px-2.5 py-2"
                          >
                            <div className="min-w-0">
                              <p className="text-xs text-zinc-300 truncate">{row.email}</p>
                              {row.submitted_at && (
                                <p className="text-[11px] text-zinc-500 mt-0.5">
                                  Submitted {new Date(row.submitted_at).toLocaleString()}
                                </p>
                              )}
                              {!row.submitted_at && row.sent_at && (
                                <p className="text-[11px] text-zinc-500 mt-0.5">
                                  Sent {new Date(row.sent_at).toLocaleString()}
                                </p>
                              )}
                              {row.status === 'failed' && row.last_error && (
                                <p className="text-[11px] text-red-400 mt-0.5">Error: {row.last_error}</p>
                              )}
                            </div>
                            <span
                              className={`ml-3 text-[10px] px-1.5 py-0.5 uppercase tracking-wider border ${
                                row.status === 'submitted'
                                  ? 'border-emerald-500/20 text-emerald-300'
                                  : row.status === 'sent'
                                  ? 'border-blue-500/20 text-blue-300'
                                  : row.status === 'failed'
                                  ? 'border-red-500/20 text-red-300'
                                  : 'border-amber-500/20 text-amber-300'
                              }`}
                            >
                              {row.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-500 mt-2">
                        No recipients yet. Use Send Requests to distribute this review.
                      </p>
                    )}
                  </div>

                  {!thread.current_state.summary &&
                    !thread.current_state.context &&
                    reviewStrengths.length === 0 &&
                    reviewGrowthAreas.length === 0 &&
                    !thread.current_state.next_steps && (
                      <div className="border border-white/10 bg-zinc-950 p-3">
                        <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
                          Starter Template
                        </p>
                        <ul className="space-y-1 text-sm text-zinc-400">
                          <li>Summary: Add a concise overview of overall performance.</li>
                          <li>Strengths: List key wins, impact, and standout behaviors.</li>
                          <li>Growth Areas: Add focused improvement opportunities.</li>
                          <li>Next Steps: Add action items, owner, and check-in timing.</li>
                        </ul>
                      </div>
                    )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {showHandbookSelectorModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-950 border border-white/10 p-6 max-w-lg w-full mx-4 shadow-xl">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-2">Select Handbook</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Choose an active handbook to send for acknowledgement signatures.
            </p>
            <div className="max-h-72 overflow-y-auto space-y-1">
              {activeHandbooks.map((handbook) => (
                <button
                  key={handbook.id}
                  onClick={() => handleSelectHandbookForSignatures(handbook)}
                  className="w-full text-left border border-white/10 hover:border-white/20 bg-zinc-900 hover:bg-zinc-800 px-3 py-2 transition-colors"
                >
                  <p className="text-sm text-zinc-100">{handbook.title}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    v{handbook.active_version} · {handbook.scope_states?.join(', ') || 'N/A'}
                  </p>
                </button>
              ))}
            </div>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => setShowHandbookSelectorModal(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <HandbookDistributeModal
        open={showHandbookDistributeModal}
        handbookId={selectedHandbook?.id ?? null}
        handbookTitle={selectedHandbook?.title}
        submitting={sendingHandbookSignatures}
        onClose={() => {
          if (!sendingHandbookSignatures) setShowHandbookDistributeModal(false);
        }}
        onSubmit={handleSendHandbookSignatures}
      />

      {/* Review requests modal */}
      {showReviewRequestsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-950 border border-white/10 p-6 max-w-lg w-full mx-4 shadow-xl">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-2">Send Anonymous Review Requests</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Add recipient emails. Each recipient will get a unique link and tracking updates will appear in this thread.
            </p>
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Recipient Emails</span>
              <textarea
                value={reviewRecipientInput}
                onChange={(e) => setReviewRecipientInput(e.target.value)}
                placeholder="manager@company.com, peer@company.com"
                rows={4}
                className="mt-1 w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-white/20"
              />
            </label>
            <label className="block mt-3">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Optional Message</span>
              <textarea
                value={reviewEmailMessage}
                onChange={(e) => setReviewEmailMessage(e.target.value)}
                placeholder="Add context for reviewers..."
                rows={3}
                className="mt-1 w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-white/20"
              />
            </label>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => setShowReviewRequestsModal(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSendReviewRequests}
                disabled={sendingReviewRequests}
                className="flex-1 px-4 py-2 text-sm bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white transition-colors flex items-center justify-center gap-2"
              >
                {sendingReviewRequests ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : null}
                Send Requests
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Finalize confirm modal */}
      {showFinalizeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-950 border border-white/10 p-6 max-w-sm w-full mx-4 shadow-xl">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-2">
              {isOfferLetter ? 'Finalize offer letter?' : isWorkbook ? 'Finalize workbook?' : isOnboarding ? 'Finalize onboarding?' : 'Finalize anonymous review?'}
            </h2>
            <p className="text-sm text-zinc-400 mb-5">
              {isOfferLetter
                ? "This will lock the document and generate a final PDF without a watermark. You won't be able to make further edits."
                : isWorkbook
                ? "This will lock the workbook and prevent further edits. You can still view the content here."
                : isOnboarding
                ? "This will lock the onboarding thread. Created employees will remain in the system."
                : "This will lock the review and prevent further edits. You can still view the final thread content."}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowFinalizeConfirm(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleFinalize}
                disabled={finalizing}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white transition-colors flex items-center justify-center gap-2"
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
