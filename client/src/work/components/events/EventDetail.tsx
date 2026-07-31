import { useState } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, Hash, HelpCircle, Loader2, XCircle } from 'lucide-react'
import { EMS_CATEGORY_LABELS, type EmsEvent } from '../../api/events'

interface EventDetailProps {
  event: EmsEvent
  canReview: boolean
  hasIncidents: boolean
  onDismiss: () => Promise<void>
  onPromote: () => void
}

function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function EventDetail({ event, canReview, hasIncidents, onDismiss, onPromote }: EventDetailProps) {
  const [dismissing, setDismissing] = useState(false)

  async function handleDismiss() {
    setDismissing(true)
    try {
      await onDismiss()
    } finally {
      setDismissing(false)
    }
  }

  const docEntries = Object.entries(event.doc).filter(
    ([, v]) => typeof v === 'string' && v.trim().length > 0,
  )

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-w-dim font-medium">
            <span>{EMS_CATEGORY_LABELS[event.category]}</span>
            {event.severity_hint && (
              <>
                <span>·</span>
                <span>{event.severity_hint} severity</span>
              </>
            )}
          </div>
          <h1 className="text-xl font-semibold text-w-text mt-1">
            {event.title || 'Untitled event'}
          </h1>
          <p className="text-xs text-w-faint mt-1.5 flex items-center gap-1.5">
            {event.channel_name && (
              <span className="flex items-center gap-0.5">
                <Hash className="w-3 h-3" />
                {event.channel_name}
              </span>
            )}
            {event.reporter_name && <span>Reported by {event.reporter_name}</span>}
            <span>{new Date(event.created_at).toLocaleString()}</span>
          </p>
        </div>

        {/* Status banner */}
        {event.status === 'promoted' && event.incident_id && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span className="flex-1">Promoted to an IR incident.</span>
            <a
              href={`/app/ir/${event.incident_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-emerald-300 hover:text-emerald-200 font-medium"
            >
              View incident
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}
        {event.status === 'dismissed' && (
          <div className="flex items-center gap-2 rounded-lg border border-w-line bg-w-surface2 px-4 py-3 text-sm text-w-dim">
            <XCircle className="w-4 h-4 shrink-0" />
            Dismissed — no further action.
          </div>
        )}
        {event.status === 'logged' && event.awaiting_reply && (
          <div className="flex items-center gap-2 rounded-lg border border-w-line bg-w-surface2 px-4 py-3 text-sm text-w-dim">
            <HelpCircle className="w-4 h-4 shrink-0" />
            Huume asked a follow-up in the channel — awaiting reply.
          </div>
        )}

        {/* Urgency banner — deterministic server-side flag (OSHA keyword
            regex or model severe judgment); admins were paged at log time. */}
        {event.urgency && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium text-red-300">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {event.urgency === 'osha'
                ? 'Possibly OSHA-reportable (29 CFR 1904.39)'
                : 'Flagged severe'}
            </div>
            <p className="text-sm text-red-200/90 mt-1.5">
              {event.urgency === 'osha'
                ? 'A fatality must be reported to OSHA within 8 hours; an in-patient hospitalization, amputation, or loss of an eye within 24 hours. OSHA hotline: 1-800-321-6742.'
                : 'Huume judged this event severe — immediate review recommended.'}
            </p>
            <p className="text-xs text-red-200/60 mt-1.5">Admins were notified when this was logged.</p>
          </div>
        )}

        {/* Incident recommendation banner — visible regardless of the incidents
            feature, so a company that hasn't bought Incidents can still see
            Huume's judgment call before deciding whether to upgrade. */}
        {event.incident_recommendation && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium text-amber-300">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              Huume recommends filing an incident
            </div>
            {event.incident_reasoning && (
              <p className="text-sm text-amber-200/90 mt-1.5">{event.incident_reasoning}</p>
            )}
            {(event.suggested_incident_type || event.suggested_severity) && (
              <p className="text-xs text-amber-200/70 mt-1.5">
                Suggested: {event.suggested_incident_type ?? '—'}
                {event.suggested_severity ? ` · ${event.suggested_severity} severity` : ''}
              </p>
            )}
          </div>
        )}

        {/* Protocol assessment — null means "never assessed", not "no". */}
        {event.protocol_qualifies !== null && (
          <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-3">
            <div className="text-sm font-medium text-sky-300">
              {event.protocol_qualifies
                ? 'Qualifies as an incident under your company protocol'
                : 'Does not qualify as an incident under your company protocol'}
            </div>
            {event.protocol_reasoning && (
              <p className="text-sm text-sky-200/90 mt-1.5">{event.protocol_reasoning}</p>
            )}
          </div>
        )}

        {/* Narrative */}
        <div>
          <h2 className="text-[10px] uppercase tracking-[0.14em] text-w-dim font-medium mb-1.5">
            Narrative
          </h2>
          <p className="text-sm text-w-text whitespace-pre-wrap">{event.narrative}</p>
        </div>

        {/* Doc sections */}
        {docEntries.length > 0 && (
          <div>
            <h2 className="text-[10px] uppercase tracking-[0.14em] text-w-dim font-medium mb-2">
              Details
            </h2>
            <dl className="space-y-2">
              {docEntries.map(([key, value]) => (
                <div key={key} className="flex gap-3 text-sm">
                  <dt className="w-32 shrink-0 text-w-dim">{humanizeKey(key)}</dt>
                  <dd className="text-w-text whitespace-pre-wrap">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {/* Actions */}
        {canReview && event.status === 'logged' && (
          <div className="flex items-center gap-3 pt-2 border-t border-w-line">
            {hasIncidents && (
              <button
                onClick={onPromote}
                className="rounded-lg bg-w-accent px-4 py-2 text-sm font-medium text-white hover:bg-w-accent-hi transition-colors"
              >
                Promote to Incident
              </button>
            )}
            <button
              onClick={handleDismiss}
              disabled={dismissing}
              className="rounded-lg px-4 py-2 text-sm text-w-dim hover:text-w-text hover:bg-w-surface2 transition-colors disabled:opacity-50 inline-flex items-center gap-2"
            >
              {dismissing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
