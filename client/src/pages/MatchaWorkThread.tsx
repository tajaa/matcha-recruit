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
} from '../types/matcha-work';
import type { HandbookListItem } from '../types';
import { handbooks, matchaWork } from '../api/client';
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
  const sections = state.sections || [];

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="bg-zinc-800/50 border border-zinc-700/60 rounded-xl p-6">
          <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold mb-1">HR Workbook</p>
          <h2 className="text-2xl font-bold text-white tracking-tight">
            {state.workbook_title || 'Untitled Workbook'}
          </h2>
          {state.company_name && (
            <p className="text-sm text-zinc-400 mt-1">{state.company_name}</p>
          )}
          {(state.industry || state.objective) && (
            <div className="flex flex-wrap gap-2 mt-4">
              {state.industry && (
                <span className="px-2 py-0.5 rounded bg-zinc-700 text-zinc-300 text-[10px] uppercase tracking-wider">
                  {state.industry}
                </span>
              )}
              {state.objective && (
                <span className="px-2 py-0.5 rounded bg-matcha-500/10 text-matcha-400 text-[10px] uppercase tracking-wider border border-matcha-500/20">
                  {state.objective}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {sections.length === 0 ? (
            <div className="bg-zinc-900/40 border border-zinc-800 border-dashed rounded-xl p-12 text-center">
              <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center mx-auto mb-4 text-zinc-600">
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
              <div key={idx} className="bg-zinc-900/60 border border-zinc-800 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-zinc-800 bg-zinc-800/30">
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
  const [savingDraft, setSavingDraft] = useState(false);
  const [creatingChat, setCreatingChat] = useState(false);
  const [showFinalizeConfirm, setShowFinalizeConfirm] = useState(false);
  const [tokenUsage, setTokenUsage] = useState<(MWTokenUsage & { stage: 'estimate' | 'final' }) | null>(null);
  const [usageSummary, setUsageSummary] = useState<MWUsageSummaryResponse | null>(null);
  const [showReviewRequestsModal, setShowReviewRequestsModal] = useState(false);
  const [sendingReviewRequests, setSendingReviewRequests] = useState(false);
  const [reviewRecipientInput, setReviewRecipientInput] = useState('');
  const [reviewEmailMessage, setReviewEmailMessage] = useState('');
  const [loadingActiveHandbooks, setLoadingActiveHandbooks] = useState(false);
  const [sendingHandbookSignatures, setSendingHandbookSignatures] = useState(false);
  const [showHandbookSelectorModal, setShowHandbookSelectorModal] = useState(false);
  const [showHandbookDistributeModal, setShowHandbookDistributeModal] = useState(false);
  const [activeHandbooks, setActiveHandbooks] = useState<HandbookListItem[]>([]);
  const [selectedHandbook, setSelectedHandbook] = useState<{ id: string; title: string } | null>(null);

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
      const [threadData, verData, usageData] = await Promise.all([
        matchaWork.getThread(threadId),
        matchaWork.getVersions(threadId),
        matchaWork.getUsageSummary(30).catch(() => null),
      ]);
      setThread(threadData);
      setMessages(threadData.messages);
      setVersions(verData);
      setUsageSummary(usageData);
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
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = async () => {
    if (!input.trim() || !threadId || sending) return;

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
            prev ? { ...prev, current_state: resp.current_state, version: resp.version } : prev
          );
          if (resp.version > 0) {
            shouldRefreshVersions = true;
          }
          if (resp.pdf_url) {
            setPdfUrl(resp.pdf_url);
            setActiveTab('preview');
          } else if (resp.current_state?.sections && resp.current_state.sections.length > 0) {
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
          return;
        }

        if (event.type === 'error') {
          streamError = event.message || 'Failed to send message';
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
      setError(err instanceof Error ? err.message : 'Failed to send message');
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
  const reviewStatuses: MWReviewRequestStatus[] = (thread?.current_state.review_request_statuses || [])
    .filter((row): row is MWReviewRequestStatus => Boolean(row && typeof row === 'object' && row.email));
  const reviewExpectedResponses = thread?.current_state.review_expected_responses ?? reviewStatuses.length;
  const reviewReceivedResponses = thread?.current_state.review_received_responses ?? reviewStatuses.filter((row) => row.status === 'submitted').length;
  const reviewPendingResponses = thread?.current_state.review_pending_responses ?? Math.max(reviewExpectedResponses - reviewReceivedResponses, 0);
  const isUnscopedChat = thread
    ? thread.version === 0 &&
      messages.length === 0 &&
      Object.keys(thread.current_state || {}).length === 0
    : false;
  const inputDisabled = isFinalized || isArchived || sending;
  const formatTokenCount = (value: number | null | undefined) =>
    value == null ? '—' : value.toLocaleString();

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
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/app/matcha/work/chats')}
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
              <span className="text-xs bg-zinc-700/60 text-zinc-300 px-1.5 py-0.5 rounded capitalize">
                {isUnscopedChat ? 'Intent-driven chat' : thread.task_type === 'review' ? 'Anonymous Review' : thread.task_type === 'workbook' ? 'HR Workbook' : 'Offer Letter'}
              </span>
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
              {thread.linked_offer_letter_id && (
                <span className="text-xs bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">
                  Draft Saved
                </span>
              )}
              {tokenUsage && (
                <span className="text-xs bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">
                  {tokenUsage.estimated ? '~' : ''}
                  {formatTokenCount(tokenUsage.total_tokens)} tokens
                </span>
              )}
            </div>
            {tokenUsage && (
              <div className="text-[11px] text-zinc-500 mt-0.5">
                Approx billed tokens ({tokenUsage.estimated ? 'estimate' : 'final'}): p{' '}
                {formatTokenCount(tokenUsage.prompt_tokens)} | c{' '}
                {formatTokenCount(tokenUsage.completion_tokens)} | t{' '}
                {formatTokenCount(tokenUsage.total_tokens)}
              </div>
            )}
            {usageSummary && usageSummary.by_model.length > 0 && (
              <div className="text-[11px] text-zinc-500 mt-0.5">
                30d tracked: {formatTokenCount(usageSummary.totals.total_tokens)} tokens across{' '}
                {usageSummary.by_model.length} model{usageSummary.by_model.length === 1 ? '' : 's'}.
                Top: {usageSummary.by_model[0].model} ({formatTokenCount(usageSummary.by_model[0].total_tokens)})
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <div className="hidden sm:flex items-center bg-zinc-800 rounded-lg p-0.5">
            <button className="px-3 py-1 text-xs rounded bg-zinc-700 text-zinc-100">
              Chat
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/chats')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Chats
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/elements')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Matcha Elements
            </button>
          </div>

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
              {isOfferLetter ? 'Preview' : isWorkbook ? 'Workbook' : 'Summary'}
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/elements')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Elements
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/chats')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Chats
            </button>
          </div>

          <button
            onClick={handleCreateChat}
            disabled={creatingChat}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v14m7-7H5" />
            </svg>
            <span>{creatingChat ? 'Creating...' : 'New Chat'}</span>
          </button>

          {isOfferLetter && !isArchived && (
            <button
              onClick={handleSaveDraft}
              disabled={savingDraft}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {savingDraft ? 'Saving...' : 'Save Draft'}
            </button>
          )}

          {isReview && !isArchived && (
            <button
              onClick={handleOpenReviewRequestsModal}
              disabled={sendingReviewRequests}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {sendingReviewRequests ? 'Sending...' : 'Send Requests'}
            </button>
          )}

          {isWorkbook && !isArchived && (
            <button
              onClick={handleOpenHandbookSignatures}
              disabled={loadingActiveHandbooks || sendingHandbookSignatures}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {loadingActiveHandbooks ? 'Loading...' : sendingHandbookSignatures ? 'Sending...' : 'Send Signatures'}
            </button>
          )}

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
                <p className="text-sm text-zinc-400 font-medium">Start chatting</p>
                <p className="text-xs text-zinc-600 mt-1 max-w-xs">
                  Tell me what you need in natural language.
                </p>
                <div className="mt-3 text-[11px] text-zinc-500 max-w-sm">
                  Default mode: US HR chat. Skills: offer letters, anonymized reviews, HR workbooks. Ask naturally and Matcha will route commands when supported.
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
                  placeholder={
                    isUnscopedChat
                      ? 'Ask for an offer letter, review, or workbook...'
                      : isReview
                      ? 'Add anonymized review details...'
                      : isWorkbook
                      ? 'Describe workbook sections or objective...'
                      : 'Describe changes or add details...'
                  }
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
            {isOfferLetter ? (
              pdfUrl ? (
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
              )
            ) : isWorkbook ? (
              <WorkbookPreview state={thread.current_state} />
            ) : (
              <div className="h-full overflow-y-auto p-4">
                <div className="max-w-2xl mx-auto bg-zinc-800/50 border border-zinc-700/60 rounded-xl p-4 space-y-4">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-500">Anonymous Review</p>
                    <h3 className="text-base font-semibold text-zinc-100 mt-1">
                      {thread.current_state.review_title || thread.current_state.review_subject || 'Untitled Review'}
                    </h3>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs bg-zinc-700 text-zinc-200 px-2 py-0.5 rounded">
                        {thread.current_state.anonymized === false ? 'Not anonymized' : 'Anonymized'}
                      </span>
                      {thread.current_state.overall_rating != null && (
                        <span className="text-xs bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded">
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

                  {toItemList(thread.current_state.strengths).length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Strengths</p>
                      <ul className="space-y-1">
                        {toItemList(thread.current_state.strengths).map((item, idx) => (
                          <li key={`${item}-${idx}`} className="text-sm text-zinc-200">
                            • {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {toItemList(thread.current_state.growth_areas).length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Growth Areas</p>
                      <ul className="space-y-1">
                        {toItemList(thread.current_state.growth_areas).map((item, idx) => (
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
                    <div className="grid grid-cols-3 gap-2">
                      <div className="rounded-md border border-zinc-700/60 bg-zinc-900/40 p-2">
                        <p className="text-[11px] text-zinc-500">Expected</p>
                        <p className="text-sm text-zinc-200 mt-0.5">{reviewExpectedResponses}</p>
                      </div>
                      <div className="rounded-md border border-zinc-700/60 bg-zinc-900/40 p-2">
                        <p className="text-[11px] text-zinc-500">Received</p>
                        <p className="text-sm text-emerald-300 mt-0.5">{reviewReceivedResponses}</p>
                      </div>
                      <div className="rounded-md border border-zinc-700/60 bg-zinc-900/40 p-2">
                        <p className="text-[11px] text-zinc-500">Pending</p>
                        <p className="text-sm text-amber-300 mt-0.5">{reviewPendingResponses}</p>
                      </div>
                    </div>
                    {reviewStatuses.length > 0 ? (
                      <div className="mt-3 space-y-1.5">
                        {reviewStatuses.map((row) => (
                          <div
                            key={row.email}
                            className="flex items-center justify-between rounded-md border border-zinc-700/50 bg-zinc-900/30 px-2.5 py-2"
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
                              className={`ml-3 text-[11px] px-1.5 py-0.5 rounded ${
                                row.status === 'submitted'
                                  ? 'bg-emerald-500/20 text-emerald-300'
                                  : row.status === 'sent'
                                  ? 'bg-blue-500/20 text-blue-300'
                                  : row.status === 'failed'
                                  ? 'bg-red-500/20 text-red-300'
                                  : 'bg-amber-500/20 text-amber-300'
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
                    toItemList(thread.current_state.strengths).length === 0 &&
                    toItemList(thread.current_state.growth_areas).length === 0 &&
                    !thread.current_state.next_steps && (
                      <div className="rounded-lg border border-zinc-700/60 bg-zinc-900/40 p-3">
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
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-lg w-full mx-4 shadow-xl">
            <h2 className="text-base font-semibold text-zinc-100 mb-2">Select Handbook</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Choose an active handbook to send for acknowledgement signatures.
            </p>
            <div className="max-h-72 overflow-y-auto space-y-2">
              {activeHandbooks.map((handbook) => (
                <button
                  key={handbook.id}
                  onClick={() => handleSelectHandbookForSignatures(handbook)}
                  className="w-full text-left rounded-lg border border-zinc-700 hover:border-zinc-500 bg-zinc-800/60 hover:bg-zinc-800 px-3 py-2 transition-colors"
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
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-zinc-700 rounded-lg transition-colors"
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
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-lg w-full mx-4 shadow-xl">
            <h2 className="text-base font-semibold text-zinc-100 mb-2">Send Anonymous Review Requests</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Add recipient emails. Each recipient will get a unique link and tracking updates will appear in this thread.
            </p>
            <label className="block">
              <span className="text-xs text-zinc-500 uppercase tracking-wide">Recipient Emails</span>
              <textarea
                value={reviewRecipientInput}
                onChange={(e) => setReviewRecipientInput(e.target.value)}
                placeholder="manager@company.com, peer@company.com"
                rows={4}
                className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-matcha-500/50"
              />
            </label>
            <label className="block mt-3">
              <span className="text-xs text-zinc-500 uppercase tracking-wide">Optional Message</span>
              <textarea
                value={reviewEmailMessage}
                onChange={(e) => setReviewEmailMessage(e.target.value)}
                placeholder="Add context for reviewers..."
                rows={3}
                className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-matcha-500/50"
              />
            </label>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => setShowReviewRequestsModal(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-zinc-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSendReviewRequests}
                disabled={sendingReviewRequests}
                className="flex-1 px-4 py-2 text-sm bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center justify-center gap-2"
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
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-sm w-full mx-4 shadow-xl">
            <h2 className="text-base font-semibold text-zinc-100 mb-2">
              {isOfferLetter ? 'Finalize offer letter?' : isWorkbook ? 'Finalize workbook?' : 'Finalize anonymous review?'}
            </h2>
            <p className="text-sm text-zinc-400 mb-5">
              {isOfferLetter
                ? "This will lock the document and generate a final PDF without a watermark. You won't be able to make further edits."
                : isWorkbook
                ? "This will lock the workbook and prevent further edits. You can still view the content here."
                : "This will lock the review and prevent further edits. You can still view the final thread content."}
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
