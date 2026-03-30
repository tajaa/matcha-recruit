import { useState, useEffect } from 'react'
import { ArrowLeft, Mail, RefreshCw, Loader2, Send, PenLine } from 'lucide-react'
import type { AgentEmail } from '../../types/matcha-work'
import { agentEmailStatus, agentFetchEmails, agentDraftReply, agentSendEmail } from '../../api/matchaWork'

export default function AgentPanel() {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [emailAddr, setEmailAddr] = useState<string | null>(null)
  const [emails, setEmails] = useState<AgentEmail[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedEmail, setSelectedEmail] = useState<AgentEmail | null>(null)

  // Draft state
  const [draftInstructions, setDraftInstructions] = useState('')
  const [draftBody, setDraftBody] = useState<string | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [sending, setSending] = useState(false)
  const [sentMessage, setSentMessage] = useState<string | null>(null)

  useEffect(() => {
    agentEmailStatus()
      .then((s) => {
        setConnected(s.connected)
        setEmailAddr(s.email)
        if (s.connected) fetchEmails()
      })
      .catch(() => setConnected(false))
  }, [])

  async function fetchEmails() {
    setLoading(true)
    try {
      const { emails: fetched } = await agentFetchEmails()
      setEmails(fetched)
    } catch {}
    setLoading(false)
  }

  async function handleDraft() {
    if (!selectedEmail || !draftInstructions.trim()) return
    setDrafting(true)
    setDraftBody(null)
    setSentMessage(null)
    try {
      const result = await agentDraftReply(selectedEmail.id, draftInstructions.trim())
      setDraftBody(result.body)
    } catch {}
    setDrafting(false)
  }

  async function handleSend() {
    if (!selectedEmail || !draftBody) return
    setSending(true)
    try {
      const subject = selectedEmail.subject.startsWith('Re:') ? selectedEmail.subject : `Re: ${selectedEmail.subject}`
      await agentSendEmail(selectedEmail.from, subject, draftBody, selectedEmail.id)
      setSentMessage('Email sent successfully')
      setDraftBody(null)
      setDraftInstructions('')
    } catch {}
    setSending(false)
  }

  // Dark editor theme (always dark)
  const c = {
    bg: '#1e1e1e',
    cardBg: '#252526',
    border: '#333',
    text: '#d4d4d4',
    heading: '#e8e8e8',
    muted: '#6a737d',
    accent: '#ce9178',
    hoverBg: '#2a2d2e',
  }

  if (connected === null) {
    return (
      <div className="hidden md:flex md:w-1/2 items-center justify-center" style={{ background: c.bg }}>
        <Loader2 size={20} className="animate-spin" style={{ color: c.muted }} />
      </div>
    )
  }

  if (!connected) {
    return (
      <div className="hidden md:flex md:w-1/2 items-center justify-center" style={{ background: c.bg }}>
        <div className="text-center">
          <Mail size={24} className="mx-auto mb-2" style={{ color: c.muted }} />
          <p className="text-xs" style={{ color: c.muted }}>Gmail not connected</p>
          <p className="text-[10px] mt-1" style={{ color: c.muted }}>
            Connect via the agent setup first
          </p>
        </div>
      </div>
    )
  }

  // Email detail view
  if (selectedEmail) {
    return (
      <div className="hidden md:flex md:w-1/2 flex-col" style={{ background: c.bg }}>
        {/* Header */}
        <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: `1px solid ${c.border}` }}>
          <button
            onClick={() => { setSelectedEmail(null); setDraftBody(null); setDraftInstructions(''); setSentMessage(null) }}
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

          {/* Draft section */}
          <div className="pt-3 space-y-2" style={{ borderTop: `1px solid ${c.border}` }}>
            <div className="flex items-center gap-2">
              <input
                value={draftInstructions}
                onChange={(e) => setDraftInstructions(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleDraft() }}
                placeholder="Instructions for reply (e.g. 'accept the meeting')"
                className="flex-1 text-xs rounded px-2.5 py-1.5 border focus:outline-none"
                style={{ background: '#1a1a1a', color: c.text, borderColor: '#555' }}
              />
              <button
                onClick={handleDraft}
                disabled={drafting || !draftInstructions.trim()}
                className="p-1.5 rounded transition-colors disabled:opacity-40"
                style={{ color: c.accent }}
              >
                {drafting ? <Loader2 size={14} className="animate-spin" /> : <PenLine size={14} />}
              </button>
            </div>

            {draftBody && (
              <div className="rounded p-3 space-y-2" style={{ background: '#1a1a1a', border: `1px solid ${c.border}` }}>
                <p className="text-[10px] font-medium" style={{ color: c.accent }}>Draft Reply</p>
                <textarea
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                  className="w-full text-xs rounded p-2 border focus:outline-none resize-none min-h-[80px]"
                  style={{ background: c.bg, color: c.text, borderColor: '#555', fontFamily: 'ui-monospace, monospace', lineHeight: 1.65 }}
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSend}
                    disabled={sending}
                    className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
                    style={{ background: '#22c55e', color: '#fff' }}
                  >
                    {sending ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
                    Send
                  </button>
                  <button
                    onClick={() => setDraftBody(null)}
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
          </div>
        </div>
      </div>
    )
  }

  // Email list view
  return (
    <div className="hidden md:flex md:w-1/2 flex-col" style={{ background: c.bg }}>
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: `1px solid ${c.border}` }}>
        <div>
          <h3 className="text-sm font-semibold" style={{ color: c.heading }}>
            <Mail size={14} className="inline mr-1.5" style={{ color: c.accent }} />
            Inbox
          </h3>
          <p className="text-[10px] mt-0.5" style={{ color: c.muted }}>
            {emailAddr ?? 'Connected'} &middot; {emails.length} unread
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
            onClick={() => setSelectedEmail(email)}
            className="px-4 py-3 cursor-pointer transition-colors"
            style={{ borderBottom: `1px solid ${c.border}` }}
            onMouseEnter={(e) => (e.currentTarget.style.background = c.hoverBg)}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <p className="text-xs font-medium truncate" style={{ color: c.heading }}>
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
          </div>
        ))}
      </div>
    </div>
  )
}
