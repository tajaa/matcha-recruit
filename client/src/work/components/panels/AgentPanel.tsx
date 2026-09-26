import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, Mail, RefreshCw, Loader2, Send, PenLine, Sparkles } from 'lucide-react'
import type { AgentEmail } from '../../types'
import { agentEmailStatus, agentConnectGmail, agentDisconnectGmail, agentFetchEmails, agentDraftReply, agentSendEmail, agentSummarizeEmail, agentTriageEmails, type AgentDraft, type AgentTriageBucket } from '../../api/matchaWork'
import { ApiError } from '../../../api/client'
import { useEntitlements } from '../../hooks/useEntitlements'
import { showPaywall } from '../../utils/paywall'
import EmailSnapshotWizard from './EmailSnapshotWizard'

// Prefill for the hand-written reply only. Send passes the subject through
// as typed, so this mirrors the server's _reply_subject rule; AI drafts still
// render the subject the server saved, never this.
function replySubject(subject: string): string {
  const clean = subject.replace(/[\r\n]+/g, ' ').trim()
  return /^re:/i.test(clean) ? clean : `Re: ${clean}`
}

const validEmailId = (id: string) => /^[A-Za-z0-9_-]{1,128}$/.test(id)

export default function AgentPanel({ showSnapshot = false }: { showSnapshot?: boolean }) {
  const { plan, can } = useEntitlements()
  const [connected, setConnected] = useState<boolean | null>(null)
  const [emailAddr, setEmailAddr] = useState<string | null>(null)
  const [emails, setEmails] = useState<AgentEmail[]>([])
  const [snapshotMax, setSnapshotMax] = useState(0)
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [selectedEmail, setSelectedEmail] = useState<AgentEmail | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [snapshotOpen, setSnapshotOpen] = useState(false)
  const [triage, setTriage] = useState<AgentTriageBucket[]>([])
  const [triaging, setTriaging] = useState(false)
  const [triageMessage, setTriageMessage] = useState('')
  const [summary, setSummary] = useState<string | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [actionError, setActionError] = useState('')

  // Draft state
  const [draftInstructions, setDraftInstructions] = useState('')
  const [draft, setDraft] = useState<AgentDraft | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [sending, setSending] = useState(false)
  const [sentMessage, setSentMessage] = useState<string | null>(null)
  const [manualTo, setManualTo] = useState('')
  const [manualSubject, setManualSubject] = useState('')
  const [manualBody, setManualBody] = useState('')

  const fetchEmails = useCallback(async () => {
    setLoading(true)
    try {
      const { emails: fetched } = await agentFetchEmails()
      setEmails(fetched)
      setSelectedIds((ids) => ids.filter((id) => fetched.some((email) => email.id === id)))
    } catch { setTriageMessage('Could not load emails. Try again.') }
    finally { setLoading(false) }
  }, [])

  const checkStatus = useCallback(() => {
    void agentEmailStatus()
      .then((s) => {
        setConnected(s.connected)
        setEmailAddr(s.email)
        setSnapshotMax(Number.isInteger(s.snapshot_max_emails) && s.snapshot_max_emails > 0 ? s.snapshot_max_emails : 0)
        if (s.connected) void fetchEmails()
      })
      .catch(() => setConnected(false))
  }, [fetchEmails])

  useEffect(() => {
    checkStatus()

    // Listen for OAuth popup completion
    function handleMessage(e: MessageEvent) {
      if (e.origin === window.location.origin && e.data === 'gmail-connected') {
        checkStatus()
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [checkStatus])

  async function handleConnect() {
    setConnecting(true)
    try {
      const { auth_url } = await agentConnectGmail()
      if (!window.open(auth_url, 'gmail-oauth', 'width=600,height=700')) setActionError('Allow popups to connect Gmail.')
    } catch { setActionError('Could not start Gmail connection. Try again.') }
    setConnecting(false)
  }

  async function handleDisconnect() {
    try {
      await agentDisconnectGmail()
      setConnected(false)
      setEmailAddr(null)
      setEmails([])
      setSelectedEmail(null)
      setSelectedIds([])
      setTriage([])
    } catch { setActionError('Could not disconnect Gmail. Try again.') }
  }

  function requireEmailAI(): boolean {
    if (plan === 'free' || (plan !== null && !can('email_ai'))) {
      showPaywall('email_ai', 'lite', plan)
      return false
    }
    return true
  }

  async function handleSummarize() {
    if (!selectedEmail || !validEmailId(selectedEmail.id) || !requireEmailAI()) return
    setSummarizing(true)
    setSummary(null)
    setActionError('')
    try { setSummary((await agentSummarizeEmail(selectedEmail.id)).summary) }
    catch { setActionError('Could not summarize this message. Try again.') }
    finally { setSummarizing(false) }
  }

  async function handleTriage(selectedOnly: boolean) {
    if (!requireEmailAI()) return
    if (selectedOnly && selectedIds.length === 0) { setTriageMessage('Select at least one email to triage.'); return }
    const ids = selectedOnly ? selectedIds : undefined
    if (ids?.some((id) => !validEmailId(id))) { setTriageMessage('One selected email has an invalid message ID.'); return }
    setTriaging(true)
    setTriageMessage('')
    try {
      setTriage((await agentTriageEmails(ids)).buckets)
      setTriageMessage('In-app suggestions only. Gmail labels and read status are unchanged.')
    } catch { setTriageMessage('Could not triage emails. Try again.') }
    finally { setTriaging(false) }
  }

  async function handleDraft() {
    if (!selectedEmail || !validEmailId(selectedEmail.id) || !requireEmailAI()) return
    setDrafting(true)
    setDraft(null)
    setSentMessage(null)
    setActionError('')
    try {
      setDraft(await agentDraftReply(selectedEmail.id, draftInstructions.trim() || undefined))
    } catch (error) {
      setActionError(error instanceof ApiError && error.status === 422 ? "Can't reply to this sender: no reply address is available."
        : error instanceof ApiError && error.status === 502 ? 'AI drafting is unavailable. Try again.'
          : 'Could not prepare a reply. Try again.')
    } finally { setDrafting(false) }
  }

  async function handleSend() {
    if (!selectedEmail || !draft?.body.trim() || !validEmailId(selectedEmail.id)) return
    setSending(true)
    setActionError('')
    try {
      await agentSendEmail({ to: draft.to, subject: draft.subject, body: draft.body, reply_to_id: selectedEmail.id, thread_id: draft.thread_id, in_reply_to: draft.in_reply_to, draft_id: draft.draft_id })
      setSentMessage('Email sent successfully')
      setDraft(null)
      setDraftInstructions('')
    } catch (error) {
      setActionError(error instanceof ApiError && error.status === 429 ? 'Gmail is rate limiting sends. Wait and try again.'
        : error instanceof ApiError && error.status === 400 ? 'The reply headers are invalid. Review the draft and try again.'
          : 'Could not send this email. Try again.')
    } finally { setSending(false) }
  }

  async function handleManualSend() {
    if (!selectedEmail || !manualTo.trim() || !manualSubject.trim() || !manualBody.trim() || !validEmailId(selectedEmail.id)) return
    setSending(true)
    setActionError('')
    try {
      const result = await agentSendEmail({ to: manualTo.trim(), subject: manualSubject.trim(), body: manualBody.trim(), reply_to_id: selectedEmail.id })
      setSentMessage(`Email sent: ${result.subject}`)
      setManualBody('')
      setDraft(null)
    } catch (error) {
      setActionError(error instanceof ApiError && error.status === 429 ? 'Gmail is rate limiting sends. Wait and try again.'
        : error instanceof ApiError && error.status === 400 ? 'The reply headers are invalid. Review the address and subject.'
          : 'Could not send this email. Try again.')
    } finally { setSending(false) }
  }

  // Follow the active workspace theme, including Espresso's light palettes.
  const c = {
    bg: 'var(--color-w-bg)',
    cardBg: 'var(--color-w-surface)',
    border: 'var(--color-w-line)',
    text: 'var(--color-w-text)',
    heading: 'var(--color-w-text)',
    muted: 'var(--color-w-dim)',
    accent: 'var(--color-w-accent)',
    hoverBg: 'var(--color-w-surface2)',
  }

  if (connected === null) {
    return (
      <div className="flex w-full items-center justify-center" style={{ background: c.bg }}>
        <Loader2 size={20} className="animate-spin" style={{ color: c.muted }} />
      </div>
    )
  }

  if (!connected) {
    return (
      <div className="flex w-full items-center justify-center" style={{ background: c.bg }}>
        <div className="text-center">
          <Mail size={24} className="mx-auto mb-3" style={{ color: c.muted }} />
          <p className="text-xs mb-3" style={{ color: c.muted }}>Connect your Gmail to get started</p>
          <button
            onClick={handleConnect}
            disabled={connecting}
            className="text-xs font-medium px-4 py-2 rounded transition-colors disabled:opacity-50"
            style={{ background: c.accent, color: 'var(--color-w-on-accent)' }}
          >
            {connecting ? 'Opening...' : 'Connect Gmail'}
          </button>
          {actionError && <p role="alert" className="mt-2 text-xs text-red-400">{actionError}</p>}
        </div>
      </div>
    )
  }

  // Email detail view
  if (selectedEmail) {
    return (
      <div className="flex w-full flex-col" style={{ background: c.bg }}>
        {/* Header */}
        <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: `1px solid ${c.border}` }}>
          <button
            onClick={() => { setSelectedEmail(null); setDraft(null); setSummary(null); setActionError(''); setDraftInstructions(''); setManualBody(''); setSentMessage(null) }}
            style={{ color: c.muted }}
            className="hover:opacity-80"
          >
            <ArrowLeft size={14} />
          </button>
          <span className="text-xs font-medium truncate" style={{ color: c.heading }}>
            {selectedEmail.subject}
          </span>
        </div>

        {/* Email content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          <div className="space-y-1">
            <p className="text-xs" style={{ color: c.accent }}>{selectedEmail.from}</p>
            <p className="text-[10px]" style={{ color: c.muted }}>{selectedEmail.date}</p>
          </div>
          <div
            className="text-xs whitespace-pre-wrap leading-relaxed"
            style={{ color: c.text, fontFamily: 'ui-monospace, monospace' }}
          >
            {selectedEmail.body}
          </div>

          <div className="rounded-md border p-3" style={{ borderColor: c.border }}>
            <div className="flex items-center gap-2"><Sparkles size={14} style={{ color: c.accent }} /><p className="flex-1 text-xs font-medium" style={{ color: c.heading }}>AI summary</p><button onClick={() => void handleSummarize()} disabled={summarizing} className="text-xs underline disabled:opacity-50" style={{ color: c.accent }}>{summarizing ? 'Summarizing…' : summary === null ? 'Summarize' : 'Retry'}</button></div>
            {summary === '' && <p className="mt-2 text-xs" style={{ color: c.muted }}>Summary unavailable right now. Try again.</p>}
            {summary && <p className="mt-2 whitespace-pre-wrap text-xs" style={{ color: c.text }}>{summary}</p>}
          </div>

          {/* Draft section */}
          <div className="pt-3 space-y-2" style={{ borderTop: `1px solid ${c.border}` }}>
            <div className="flex items-center gap-2">
              <input
                value={draftInstructions}
                onChange={(e) => setDraftInstructions(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void handleDraft() }}
                placeholder="Instructions for reply (e.g. 'accept the meeting')"
                className="flex-1 text-xs rounded px-2.5 py-1.5 border focus:outline-none"
                style={{ background: c.cardBg, color: c.text, borderColor: c.border }}
              />
              <button
                onClick={handleDraft}
                disabled={drafting}
                aria-label="Draft AI reply"
                className="p-1.5 rounded transition-colors disabled:opacity-40"
                style={{ color: c.accent }}
              >
                {drafting ? <Loader2 size={14} className="animate-spin" /> : <PenLine size={14} />}
              </button>
            </div>

            {draft && (
              <div className="rounded p-3 space-y-2" style={{ background: c.cardBg, border: `1px solid ${c.border}` }}>
                <p className="text-[10px] font-medium" style={{ color: c.accent }}>Draft Reply · {draft.subject}</p>
                <p className="text-[10px]" style={{ color: c.muted }}>To {draft.to}</p>
                <textarea
                  value={draft.body}
                  onChange={(e) => setDraft((current) => current ? { ...current, body: e.target.value } : current)}
                  className="w-full text-xs rounded p-2 border focus:outline-none resize-none min-h-[80px]"
                  style={{ background: c.bg, color: c.text, borderColor: c.border, fontFamily: 'ui-monospace, monospace', lineHeight: 1.65 }}
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => void handleSend()}
                    disabled={sending || !draft.body.trim()}
                    className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
                    style={{ background: c.accent, color: 'var(--color-w-on-accent)' }}
                  >
                    {sending ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
                    Send
                  </button>
                  <button
                    onClick={() => setDraft(null)}
                    className="text-[10px]"
                    style={{ color: c.muted }}
                  >
                    Discard
                  </button>
                </div>
              </div>
            )}

            {sentMessage && (
              <p className="text-[10px] font-medium" style={{ color: '#22c55e' }}>{sentMessage}</p>
            )}
            {actionError && <p role="alert" className="text-xs text-red-400">{actionError}</p>}
          </div>

          <div className="space-y-2 border-t pt-3" style={{ borderColor: c.border }}>
            <p className="text-xs font-medium" style={{ color: c.heading }}>Write your own reply</p>
            <label className="block text-[10px]" style={{ color: c.muted }}>To<input value={manualTo} onChange={(event) => setManualTo(event.target.value)} className="mt-1 block w-full rounded border px-2 py-1 text-xs" style={{ background: c.cardBg, color: c.text, borderColor: c.border }} /></label>
            <label className="block text-[10px]" style={{ color: c.muted }}>Subject<input value={manualSubject} onChange={(event) => setManualSubject(event.target.value)} className="mt-1 block w-full rounded border px-2 py-1 text-xs" style={{ background: c.cardBg, color: c.text, borderColor: c.border }} /></label>
            <label className="block text-[10px]" style={{ color: c.muted }}>Message<textarea value={manualBody} onChange={(event) => setManualBody(event.target.value)} className="mt-1 block min-h-20 w-full resize-y rounded border px-2 py-1 text-xs" style={{ background: c.cardBg, color: c.text, borderColor: c.border }} /></label>
            <button onClick={() => void handleManualSend()} disabled={sending || !manualTo.trim() || !manualSubject.trim() || !manualBody.trim()} className="rounded px-3 py-1.5 text-xs font-medium disabled:opacity-40" style={{ background: c.accent, color: 'var(--color-w-on-accent)' }}>Send my reply</button>
          </div>
        </div>
      </div>
    )
  }

  // Email list view
  return (
    <div className="flex w-full flex-col" style={{ background: c.bg }}>
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: `1px solid ${c.border}` }}>
        <div>
          <h3 className="text-sm font-semibold" style={{ color: c.heading }}>
            <Mail size={14} className="inline mr-1.5" style={{ color: c.accent }} />
            Inbox
          </h3>
          <p className="text-[10px] mt-0.5" style={{ color: c.muted }}>
            {emailAddr ?? 'Connected'} &middot; {emails.length} unread
            <button onClick={handleDisconnect} className="ml-2 underline opacity-60 hover:opacity-100">
              disconnect
            </button>
          </p>
        </div>
        <button
          onClick={fetchEmails}
          disabled={loading}
          className="p-1.5 rounded transition-colors"
          style={{ color: c.muted }}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2" style={{ borderColor: c.border }}>
        <button onClick={() => void handleTriage(false)} disabled={triaging || emails.length === 0} className="rounded border px-2 py-1 text-[10px] disabled:opacity-40" style={{ borderColor: c.border, color: c.accent }}>Triage unread</button>
        <button onClick={() => void handleTriage(true)} disabled={triaging} className="rounded border px-2 py-1 text-[10px] disabled:opacity-40" style={{ borderColor: c.border, color: c.accent }}>Triage selected</button>
        {showSnapshot && <button onClick={() => setSnapshotOpen(true)} className="rounded border px-2 py-1 text-[10px]" style={{ borderColor: c.border, color: c.accent }}>Send to task</button>}
        {triaging && <Loader2 size={12} className="animate-spin" style={{ color: c.muted }} />}
      </div>
      {triageMessage && <p role="status" className="px-4 py-2 text-[10px]" style={{ color: c.muted }}>{triageMessage}</p>}
      {actionError && <p role="alert" className="px-4 py-2 text-xs text-red-400">{actionError}</p>}

      {/* Email list */}
      <div className="flex-1 overflow-y-auto">
        {loading && emails.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={16} className="animate-spin" style={{ color: c.muted }} />
          </div>
        )}

        {!loading && emails.length === 0 && (
          <div className="text-center py-12">
            <p className="text-xs" style={{ color: c.muted }}>No unread emails</p>
          </div>
        )}

        {emails.map((email) => (
          <div
            key={email.id}
            onClick={() => { setSelectedEmail(email); setSummary(null); setDraft(null); setManualTo(email.from); setManualSubject(replySubject(email.subject)); setManualBody(''); setActionError('') }}
            className="flex cursor-pointer items-start gap-2 px-4 py-3 transition-colors"
            style={{ borderBottom: `1px solid ${c.border}` }}
            onMouseEnter={(e) => (e.currentTarget.style.background = c.hoverBg)}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <input type="checkbox" aria-label={`Select ${email.subject}`} checked={selectedIds.includes(email.id)} onClick={(event) => event.stopPropagation()} onChange={(event) => setSelectedIds((ids) => event.target.checked ? [...ids, email.id] : ids.filter((id) => id !== email.id))} className="mt-1 shrink-0" />
            <div className="min-w-0 flex-1"><p className="text-xs font-medium truncate" style={{ color: c.heading }}>
              {email.from.replace(/<.*>/, '').trim()}
            </p>
            <p className="text-xs truncate mt-0.5" style={{ color: c.text }}>
              {email.subject}
            </p>
            <p className="text-[10px] mt-0.5 truncate" style={{ color: c.muted }}>
              {email.body.slice(0, 100)}...
            </p>
            <p className="text-[10px] mt-1" style={{ color: c.muted }}>
              {email.date}
            </p>
            {triage.find((bucket) => bucket.email_id === email.id) && <p className="mt-1 text-[10px] capitalize" style={{ color: c.accent }}>{triage.find((bucket) => bucket.email_id === email.id)?.bucket.replaceAll('_', ' ')} · {triage.find((bucket) => bucket.email_id === email.id)?.reason}</p>}</div>
          </div>
        ))}
      </div>
      {snapshotOpen && <EmailSnapshotWizard emails={emails} maxEmails={snapshotMax} initialIds={selectedIds} onClose={() => setSnapshotOpen(false)} />}
    </div>
  )
}
