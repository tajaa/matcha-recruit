import { AlertTriangle, ShieldAlert, ShieldCheck, Loader2 } from 'lucide-react'
import { Textarea } from '../../components/ui'
import type { ComplianceVerdict } from '../../api/discipline'

type Props = {
  verdict: ComplianceVerdict | null
  loading?: boolean
  ackReason: string
  onAckReasonChange: (v: string) => void
}

/**
 * Renders the compliance verdict above the Issue button.
 *
 * Blocks and advisories are deliberately styled as different *kinds* of thing,
 * not two shades of warning. A block is a statute saying no — there is no
 * acknowledge box under it, because there is no lawful way to proceed. An
 * advisory is a risk HR weighs and documents. Collapsing the two into one
 * "warnings" list is how the important one gets clicked through.
 */
export default function CompliancePanel({
  verdict,
  loading,
  ackReason,
  onAckReasonChange,
}: Props) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Checking state leave protections…
      </div>
    )
  }

  if (!verdict) return null

  const { blocks, advisories } = verdict
  const clean = blocks.length === 0 && advisories.length === 0

  if (clean) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-emerald-900/50 bg-emerald-950/30 p-3">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        <div className="text-sm text-emerald-200">
          No protected-leave conflict found for these dates
          {verdict.state_row ? ` under ${verdict.state_row.statute}` : ''}.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {blocks.length > 0 && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 p-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 shrink-0 text-red-400" />
            <div className="text-sm font-semibold text-red-200">
              This action cannot be issued
            </div>
          </div>
          <ul className="mt-2 space-y-2">
            {blocks.map((b, i) => (
              <li key={i} className="text-sm text-red-200/90">
                {b.detail}
                <div className="mt-1 text-xs text-red-300/70">
                  {b.statute} · {b.state} · protected record {b.record_id.slice(0, 8)}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-3 border-t border-red-900/60 pt-2 text-xs text-red-300/80">
            Following your attendance policy does not cure this — the statute bars the
            discipline regardless. Correct the leave record if it is wrong, or discipline
            only the dates that are not protected.
          </div>
        </div>
      )}

      {advisories.length > 0 && (
        <div className="rounded-lg border border-amber-800/70 bg-amber-950/30 p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
            <div className="text-sm font-semibold text-amber-200">
              Review before issuing ({advisories.length})
            </div>
          </div>
          <ul className="mt-2 space-y-2">
            {advisories.map((a, i) => (
              <li key={i} className="text-sm text-amber-100/90">
                {a.detail}
              </li>
            ))}
          </ul>

          {blocks.length === 0 && (
            <div className="mt-3 border-t border-amber-900/60 pt-3">
              <Textarea
                label="Why are you proceeding? (recorded on the audit log)"
                placeholder="e.g. The absence on 3/12 is unrelated to the approved leave; documented separately."
                value={ackReason}
                onChange={(e) => onAckReasonChange(e.target.value)}
                rows={2}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
