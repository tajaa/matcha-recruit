import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Loader2, X } from 'lucide-react'
import { agentEmailStatus } from '../../api/matchaWork/agent'
import type { SalesProspect } from '../../api/matchaWork/sales'
import { composeBody, footerProblem } from './salesLogic'

/**
 * The batch exactly as it will go out: each recipient, subject, and body with
 * the campaign footer, from the person's own Gmail. Approving sends the
 * versions shown (their review tokens); if any changed since, the server
 * refuses the batch and nothing is sent. Each person gets their own email.
 */
export default function ReviewSend({ drafts, footer, busy, error, connectionsPath, onApprove, onClose }: {
  drafts: SalesProspect[]
  footer: string
  busy: boolean
  /** Why the server refused the last approval, shown here, over the page. */
  error: string | null
  /** Where Gmail is connected (Connections). */
  connectionsPath: string
  onApprove: (sender: string, requestId: string) => Promise<boolean>
  onClose: () => void
}) {
  const [gmail, setGmail] = useState<{ connected: boolean; email: string | null } | null>(null)
  const [read, setRead] = useState(false)
  // One approval per opened review: a double click or a retry is the same request.
  const [requestId] = useState(() => crypto.randomUUID())
  const problem = footerProblem(footer)
  const flagged = drafts.filter((d) => (d.review_flags ?? []).length > 0)

  useEffect(() => {
    let live = true
    agentEmailStatus()
      .then((s) => { if (live) setGmail({ connected: s.connected, email: s.email }) })
      .catch(() => { if (live) setGmail({ connected: false, email: null }) })
    return () => { live = false }
  }, [])

  const sender = gmail?.connected ? gmail.email : null
  const ready = !!sender && !problem && read && !busy && drafts.length > 0

  return (
    <div role="dialog" aria-modal="true" aria-label="Review and send"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex max-h-full w-full max-w-2xl flex-col rounded-xl border border-w-line bg-w-surface">
        <header className="flex items-center gap-2 border-b border-w-line px-4 py-3">
          <h2 className="flex-1 text-sm font-semibold text-w-text">
            Review {drafts.length} {drafts.length === 1 ? 'message' : 'messages'}
          </h2>
          <button type="button" onClick={onClose} aria-label="Close review" className="rounded p-1 text-w-dim hover:bg-w-surface2"><X size={14} /></button>
        </header>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {gmail === null ? (
            <p className="flex items-center gap-1.5 text-xs text-w-dim"><Loader2 size={12} className="animate-spin" />Checking your Gmail…</p>
          ) : sender ? (
            <p className="text-xs text-w-text">From <span className="font-semibold">{sender}</span>, one email per person, paced to stay inside Gmail's limits.</p>
          ) : (
            <p role="alert" className="text-xs text-red-400">
              Connect Gmail to send. <Link to={connectionsPath} className="underline">Connections</Link>
            </p>
          )}
          {problem && <p role="alert" className="text-xs text-red-400">{problem} Open the campaign's settings to add it.</p>}
          {error && (
            <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/5 px-2.5 py-1.5 text-xs text-red-400">
              {error} The messages below are the current versions.
            </p>
          )}
          {drafts.length === 0 && <p className="text-xs text-w-dim">None of the selected messages can be sent any more.</p>}
          {flagged.length > 0 && (
            <p className="flex items-start gap-1.5 text-[11px] text-amber-400">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              {flagged.length === 1 ? '1 message has' : `${flagged.length} messages have`} something to check, marked below.
            </p>
          )}
          {drafts.map((d) => (
            <article key={d.id} className="space-y-1 rounded-lg border border-w-line p-3">
              <p className="text-[11px] text-w-dim">To {d.name ? `${d.name} <${d.email}>` : d.email}</p>
              <p className="text-xs font-semibold text-w-text">{d.subject}</p>
              <p className="whitespace-pre-wrap text-xs leading-5 text-w-text">{composeBody(d.body, footer)}</p>
              {(d.review_flags ?? []).map((flag) => (
                <p key={flag} className="text-[11px] text-amber-400">• {flag}</p>
              ))}
            </article>
          ))}
        </div>
        <footer className="space-y-2 border-t border-w-line px-4 py-3">
          <label className="flex items-center gap-2 text-xs text-w-text">
            <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
            I've read every message above
          </label>
          <div className="flex items-center gap-2">
            <button type="button" disabled={!ready}
              onClick={() => { if (sender) void onApprove(sender, requestId) }}
              className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
              Send {drafts.length}
            </button>
            <button type="button" onClick={onClose} className="text-xs text-w-dim hover:text-w-text">Cancel</button>
          </div>
        </footer>
      </div>
    </div>
  )
}
