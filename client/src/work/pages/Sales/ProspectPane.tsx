import { useState } from 'react'
import { AlertTriangle, ExternalLink, X } from 'lucide-react'
import type { ProspectChanges, SalesProspect, SalesStage } from '../../api/matchaWork/sales'
import { FIT_LABEL, SEGMENT_LABEL, SERVICE_LABEL, STATUS_LABEL, composeBody } from './salesLogic'

const EDITABLE = new Set(['prospect', 'draft', 'failed'])
const STAGES: SalesStage[] = ['lead', 'qualified', 'proposal', 'negotiation', 'closed']
const input = 'w-full rounded-md border border-w-line bg-w-surface2/50 px-2.5 py-1.5 text-xs text-w-text outline-none focus:border-w-accent/60'

/**
 * One prospect: why they are worth writing to (consulting campaigns), the
 * research and where it came from, and the draft. Saving sends the version
 * the person opened, so a draft Espresso changed meanwhile isn't overwritten.
 */
export default function ProspectPane({ prospect, footer, busy, onSave, onOptOut, onDelete, onResolve, onClose }: {
  prospect: SalesProspect
  footer: string
  busy: boolean
  onSave: (changes: ProspectChanges) => Promise<boolean>
  onOptOut: () => Promise<boolean>
  onDelete: () => Promise<boolean>
  onResolve: (outcome: 'sent' | 'not_sent') => Promise<boolean>
  onClose: () => void
}) {
  const [email, setEmail] = useState(prospect.email)
  const [subject, setSubject] = useState(prospect.subject)
  const [body, setBody] = useState(prospect.body)
  const editable = EDITABLE.has(prospect.status)
  const changed = email !== prospect.email || subject !== prospect.subject || body !== prospect.body
  const flags = prospect.review_flags ?? []
  const who = prospect.name || prospect.company || prospect.email || prospect.website

  async function save() {
    const changes: ProspectChanges = { review_token: prospect.review_token }
    if (email !== prospect.email) changes.email = email.trim()
    if (subject !== prospect.subject) changes.subject = subject.trim()
    if (body !== prospect.body) changes.body = body
    await onSave(changes)
  }

  return (
    <section aria-label={`Prospect ${who}`} className="space-y-4 p-4">
      <header className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-w-text">{who}</h2>
          <p className="truncate text-[11px] text-w-dim">
            {[prospect.name && prospect.company, STATUS_LABEL[prospect.status]].filter(Boolean).join(' · ')}
          </p>
          {prospect.website && (
            <a href={prospect.website} target="_blank" rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-[11px] text-w-accent hover:underline">
              {prospect.website.replace(/^https?:\/\//, '')}<ExternalLink size={10} />
            </a>
          )}
        </div>
        <button type="button" onClick={onClose} aria-label="Close prospect" className="rounded p-1 text-w-dim hover:bg-w-surface2">
          <X size={14} />
        </button>
      </header>

      {(prospect.signal || prospect.segment || prospect.service || prospect.fit) && (
        <div className="space-y-1 rounded-md bg-w-surface2/60 p-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-w-dim">Why now</p>
          {prospect.signal && <p className="text-xs leading-5 text-w-text">{prospect.signal}</p>}
          <p className="text-[11px] text-w-dim">
            {[prospect.fit ? FIT_LABEL[prospect.fit] : '', prospect.segment ? SEGMENT_LABEL[prospect.segment] : '',
              prospect.service ? SERVICE_LABEL[prospect.service] : ''].filter(Boolean).join(' · ')}
          </p>
        </div>
      )}

      {prospect.research && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-w-dim">Research</p>
          <p className="whitespace-pre-wrap text-xs leading-5 text-w-text">{prospect.research}</p>
        </div>
      )}
      {prospect.sources.length > 0 && (
        <ul className="space-y-0.5">
          {prospect.sources.map((url) => (
            <li key={url} className="truncate">
              <a href={url} target="_blank" rel="noreferrer noopener" className="text-[11px] text-w-accent hover:underline">{url}</a>
            </li>
          ))}
        </ul>
      )}
      {prospect.notes && <p className="whitespace-pre-wrap text-[11px] text-w-dim">Notes: {prospect.notes}</p>}

      {flags.length > 0 && (
        <div role="note" className="space-y-1 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5">
          <p className="flex items-center gap-1 text-[11px] font-semibold text-amber-400"><AlertTriangle size={11} />Check before sending</p>
          {flags.map((flag) => <p key={flag} className="text-[11px] leading-4 text-w-text">• {flag}</p>)}
        </div>
      )}

      <div className="space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-w-dim">Message</p>
        {editable ? (
          <>
            <input aria-label="Email address" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email address" className={input} />
            <input aria-label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} placeholder="Subject" className={input} />
            <textarea aria-label="Message" value={body} onChange={(e) => setBody(e.target.value)} rows={10} maxLength={12000} className={input} />
            <button type="button" onClick={() => void save()} disabled={busy || !changed}
              className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
              Save draft
            </button>
          </>
        ) : (
          <div className="rounded-md bg-w-surface2/60 p-2.5">
            <p className="text-[11px] text-w-dim">To {prospect.email || '—'}</p>
            <p className="text-xs font-semibold text-w-text">{prospect.subject}</p>
            <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-w-text">{composeBody(prospect.body, footer)}</p>
          </div>
        )}
      </div>

      {prospect.status === 'unknown' && (
        <div className="space-y-1.5 rounded-md border border-w-line p-2.5">
          <p className="text-[11px] text-w-text">We couldn't confirm this message went out. Check Gmail's Sent folder, then:</p>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => void onResolve('sent')}
              className="rounded-md border border-w-line px-2.5 py-1 text-[11px] font-semibold text-w-text hover:bg-w-surface2">It was sent</button>
            <button type="button" disabled={busy} onClick={() => void onResolve('not_sent')}
              className="rounded-md border border-w-line px-2.5 py-1 text-[11px] font-semibold text-w-text hover:bg-w-surface2">Not sent: back to draft</button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-w-line pt-3">
        <label className="flex items-center gap-1.5 text-[11px] text-w-dim">
          Stage
          <select value={prospect.stage} disabled={busy} onChange={(e) => void onSave({ stage: e.target.value as SalesStage })}
            className="rounded border border-w-line bg-w-surface2/50 px-1.5 py-0.5 text-[11px] text-w-text">
            {STAGES.map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
          </select>
        </label>
        {prospect.status !== 'opted_out' && (
          <button type="button" disabled={busy}
            onClick={() => { if (window.confirm(`Never email ${prospect.email || who} again, from any of your campaigns?`)) void onOptOut() }}
            className="text-[11px] text-w-dim hover:text-w-text">Do not contact</button>
        )}
        {!['approved', 'claimed'].includes(prospect.status) && (
          <button type="button" disabled={busy}
            onClick={() => { if (window.confirm(`Delete ${who} from this campaign?`)) void onDelete() }}
            className="text-[11px] text-red-400 hover:underline">Delete</button>
        )}
      </div>
    </section>
  )
}
