import { PAYMENT_SCHEDULES, fmtCents, type CollabTerms } from '../types'

const HIGHLIGHT = 'bg-amber-500/10 ring-1 ring-amber-500/30 rounded px-1'

function changed(a: unknown, b: unknown) {
  return JSON.stringify(a) !== JSON.stringify(b)
}

function Row({ label, children, dirty }: { label: string; children: React.ReactNode; dirty?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-zinc-500">{label}</dt>
      <dd className={`text-right text-zinc-200 ${dirty ? HIGHLIGHT : ''}`}>{children}</dd>
    </div>
  )
}

function usageSentence(terms: CollabTerms): string {
  if (terms.usage_rights.scope === 'organic') return 'Organic only — no paid usage rights'
  const months = terms.usage_rights.duration_months ?? '?'
  const wl = terms.usage_rights.whitelisting ? ', including whitelisting/ads' : ''
  return `Paid usage for ${months} month${months === 1 ? '' : 's'}${wl}`
}

function exclusivitySentence(terms: CollabTerms): string {
  if (!terms.exclusivity) return 'None'
  return `${terms.exclusivity.category}, ${terms.exclusivity.duration_months} month${terms.exclusivity.duration_months === 1 ? '' : 's'}`
}

// Shared term-sheet renderer, both for a brand-side offer composer preview
// and the negotiation history on OfferDetailPage. `previous` (the prior
// revision's terms) triggers a per-field diff highlight.
export default function TermSheet({ terms, previous }: { terms: CollabTerms; previous?: CollabTerms | null }) {
  const schedule = PAYMENT_SCHEDULES.find((s) => s.value === terms.payment_schedule)

  return (
    <dl className="divide-y divide-zinc-800">
      <Row label="Compensation" dirty={previous ? changed(terms.compensation_cents, previous.compensation_cents) : false}>
        {terms.compensation_cents > 0 ? fmtCents(terms.compensation_cents) : 'Gifting (no payment)'}
      </Row>
      <Row label="Payment schedule" dirty={previous ? changed(terms.payment_schedule, previous.payment_schedule) : false}>
        {schedule?.label ?? terms.payment_schedule}
      </Row>
      <Row label="Deliverables" dirty={previous ? changed(terms.deliverables, previous.deliverables) : false}>
        <ul className="space-y-0.5">
          {terms.deliverables.map((d, i) => (
            <li key={i}>
              {d.quantity}× {d.type} on {d.platform}
              {d.due_date ? ` · due ${d.due_date}` : ''}
            </li>
          ))}
        </ul>
      </Row>
      <Row label="Usage rights" dirty={previous ? changed(terms.usage_rights, previous.usage_rights) : false}>
        {usageSentence(terms)}
      </Row>
      <Row label="Exclusivity" dirty={previous ? changed(terms.exclusivity, previous.exclusivity) : false}>
        {exclusivitySentence(terms)}
      </Row>
      <Row label="Revision rounds" dirty={previous ? changed(terms.revision_rounds, previous.revision_rounds) : false}>
        {terms.revision_rounds}
      </Row>
      <Row label="Approval required" dirty={previous ? changed(terms.approval_required, previous.approval_required) : false}>
        {terms.approval_required ? 'Yes' : 'No'}
      </Row>
      <Row label="FTC disclosure">Always required</Row>
      {(terms.start_date || terms.end_date) && (
        <Row label="Dates" dirty={previous ? changed([terms.start_date, terms.end_date], [previous.start_date, previous.end_date]) : false}>
          {terms.start_date ?? '?'} – {terms.end_date ?? '?'}
        </Row>
      )}
      {terms.notes && (
        <Row label="Notes" dirty={previous ? changed(terms.notes, previous.notes) : false}>
          <span className="whitespace-pre-wrap">{terms.notes}</span>
        </Row>
      )}
    </dl>
  )
}
