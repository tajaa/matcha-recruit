import type { ReactNode } from 'react'
import { AlertTriangle, ArrowRight, CircleCheck, CircleSlash, MessageSquareText, Search } from 'lucide-react'
import { LABEL } from '../../ui'
import type { AutopilotDemandModel, ScheduleComplianceStatus, ScheduleReview } from '../../../types/employeeSchedule'
import { fmtDayLabel, fmtTime } from '../../../types/employeeSchedule'
import { LoadBar, POLICY_WEEKLY_MINUTES } from './LoadLedger'
import ApprovalVerdict from './ApprovalVerdict'
import { askAbout, compareReviews, costDeltaLabel, costLabel, hoursLabel } from './reviewShape'
import { approvalVerdict, groupFindings, type VerdictFix } from './reviewVerdict'

export interface ReviewPaneProps {
  review: ScheduleReview | null
  title: string
  subtitle?: string | null
  /** Per-person caps from the planning inputs, so the ledger draws the same
   *  marks the rail does. */
  caps?: Record<string, { max_weekly_minutes: number | null; allow_overtime: boolean }>
  policyMinutes?: number
  /** A second scenario to compare against — the pane switches to a diff. */
  compare?: { label: string; review: ScheduleReview } | null
  actions?: ReactNode
  emptyHint?: string
  onShowShift?(shiftId: string): void
  onAskHuume?(text: string): void
  /** A proposal that is not on the board yet (a generated week) can be
   *  looked at there before approving. */
  onShowWeek?(): void
  onSelectPerson?(employeeId: string): void
  /** Approve / Cancel the staged action from here. They send the same thread
   *  turn the chat strip does, so the server's two-turn confirm still guards. */
  onApprove?(): void
  onCancel?(): void
  decisionDisabled?: boolean
}

const KIND_LABEL: Record<ScheduleReview['kind'], string> = {
  edit: 'Schedule change', create: 'New shifts', batch: 'Correction', week_draft: 'Generated week',
}

const COMPLIANCE_TONE: Record<ScheduleComplianceStatus, { className: string; label: string }> = {
  verified: { className: 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200', label: 'Law on file · no statutory advisories' },
  advisory: { className: 'border-amber-500/30 bg-amber-500/[0.06] text-amber-200', label: 'Law on file · statutory advisories attached' },
  unmapped: { className: 'border-amber-500/40 bg-amber-500/[0.1] text-amber-100', label: 'Legality NOT verified' },
  unavailable: { className: 'border-red-500/40 bg-red-500/[0.08] text-red-200', label: 'State rules could not be loaded' },
}

function when(startsAt: string | null, endsAt: string | null): string {
  if (!startsAt) return ''
  return `${fmtDayLabel(startsAt)} ${fmtTime(startsAt)}${endsAt ? `–${fmtTime(endsAt)}` : ''}`
}

/** Evidence, not the verdict: collapsed by default on a big proposal (a
 *  generated week is 28+ rows), open on a small change where the list IS the
 *  change. Native `<details>` so it needs no state and keyboard works. */
function Block({ label, count, tone, open = true, children }: { label: string; count: number; tone?: 'ok' | 'warn' | 'bad'; open?: boolean; children: ReactNode }) {
  if (count === 0) return null
  const color = tone === 'bad' ? 'text-red-300' : tone === 'warn' ? 'text-amber-300' : 'text-zinc-300'
  return (
    <details open={open} className="group/block border-t border-white/[0.06] px-4 py-3">
      <summary className="mb-2 flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden">
        <span className="text-[10px] text-zinc-600 transition-transform group-open/block:rotate-90" aria-hidden>▶</span>
        <span className={LABEL}>{label}</span>
        <span className={`font-mono text-[10px] tabular-nums ${color}`}>{count}</span>
      </summary>
      {children}
    </details>
  )
}

function RowActions({ shiftId, ask, onShowShift, onAskHuume }: { shiftId?: string | null; ask?: string; onShowShift?(id: string): void; onAskHuume?(text: string): void }) {
  return (
    <span className="ml-auto flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
      {shiftId && onShowShift && (
        <button type="button" onClick={() => onShowShift(shiftId)} className="rounded p-1 text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100" aria-label="Show this shift on the board" title="Show on board"><Search className="h-3 w-3" /></button>
      )}
      {ask && onAskHuume && (
        <button type="button" onClick={() => onAskHuume(ask)} className="rounded p-1 text-zinc-500 hover:bg-white/[0.06] hover:text-emerald-300" aria-label="Ask Huume about this" title="Ask Huume about this"><MessageSquareText className="h-3 w-3" /></button>
      )}
    </span>
  )
}

function DemandModelBlock({ model, open }: { model: AutopilotDemandModel; open: boolean }) {
  return (
    <details open={open} className="group/block mt-3 border-t border-emerald-500/15 bg-emerald-500/[0.025] px-4 py-3" aria-label="Autopilot demand model">
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-2 [&::-webkit-details-marker]:hidden">
        <span className="text-[10px] text-zinc-600 transition-transform group-open/block:rotate-90" aria-hidden>▶</span>
        <span className={LABEL}>Autopilot demand</span>
        <span className="text-xs text-emerald-200">{model.confidence} confidence</span>
        <span className="text-[11px] text-zinc-500">{model.sentence}</span>
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-[11px]">
          <thead className="text-zinc-600"><tr><th className="pb-1 font-medium">Day</th><th className="pb-1 font-medium">Window</th><th className="pb-1 font-medium">Forecast</th><th className="pb-1 font-medium">Index</th><th className="pb-1 font-medium">Weather</th><th className="pb-1 font-medium">Hours</th><th className="pb-1 text-right font-medium">Shifts</th></tr></thead>
          <tbody className="divide-y divide-white/[0.04]">
            {model.days.map((day) => (
              <tr key={day.date} className="text-zinc-400">
                <td className="py-1.5 text-zinc-200">{day.weekday.slice(0, 3)}</td>
                <td>{day.closed ? 'Closed' : day.window_with_buffers}</td>
                <td>{day.forecast_sales == null ? '—' : `$${Math.round(day.forecast_sales).toLocaleString()}`}</td>
                <td>{day.sales_index == null ? '—' : `${day.sales_index.toFixed(2)}×`}</td>
                <td>{[day.weather.condition?.replaceAll('_', ' ').toLowerCase(), day.weather.precip_probability == null ? null : `${day.weather.precip_probability}%`].filter(Boolean).join(' · ') || '—'}</td>
                <td>{day.labor_hours_target ?? '—'} → {day.labor_hours_planned}h</td>
                <td className="text-right">{day.shifts_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {model.notes.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[11px] text-zinc-500">{model.notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul>}
      {/* The per-day "why" (forecast method, weather trim, floor, roster clip)
          lives on each day, verbatim from the server — never re-worded here. */}
      {model.days.some((day) => day.notes?.length) && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-zinc-500" aria-label="Autopilot day notes">
          {model.days.filter((day) => day.notes?.length).map((day) => (
            <li key={day.date}><span className="text-zinc-300">{day.weekday.slice(0, 3)}:</span> {day.notes.join('; ')}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[10px] text-zinc-600">Used: {model.inputs_used.join(', ')}{model.inputs_missing.length ? ` · Missing: ${model.inputs_missing.join(', ')}` : ''}{model.labor?.labor_pct != null ? ` · Scheduled labor ${model.labor.labor_pct}% of forecast sales` : model.labor?.note ? ` · ${model.labor.note}` : ''}</p>
    </details>
  )
}

/** Pure over a `ScheduleReview`. The same component renders a Huume-staged
 *  change (schedule_change or generated week), a fill scenario, and the
 *  result after apply — one truth, three sources. Never writes copy about
 *  legality of its own: the compliance banner is the server's sentence. */
export default function ReviewPane({ review, title, subtitle, caps, policyMinutes = POLICY_WEEKLY_MINUTES, compare, actions, emptyHint, onShowShift, onAskHuume, onShowWeek, onSelectPerson, onApprove, onCancel, decisionDisabled }: ReviewPaneProps) {
  if (!review) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center gap-2 px-6 text-center">
        <div className={LABEL}>Review</div>
        <p className="max-w-[46ch] text-sm leading-relaxed text-zinc-500">
          {emptyHint ?? 'Nothing is staged. Ask Huume for a change, or run a scenario from the strip above, and what it would do appears here before anything is written.'}
        </p>
      </div>
    )
  }

  const tone = COMPLIANCE_TONE[review.compliance_status] ?? COMPLIANCE_TONE.unmapped
  const staged = review.assignments.filter((item) => item.verdict !== 'blocked')
  const diff = compare ? compareReviews(review, compare.review) : null
  const verdict = approvalVerdict(review, caps, policyMinutes)
  const findingGroups = groupFindings(review.findings)
  // Small change: the rows ARE the change, show them. Big proposal: the
  // verdict and the board carry it, the rows are evidence.
  const evidenceOpen = staged.length + review.unfilled.length + review.rejected.length <= 8
  const fix = (target: VerdictFix) => {
    if (target.kind === 'board') onShowShift?.(target.shiftId)
    else if (target.kind === 'person') onSelectPerson?.(target.employeeId)
    else onAskHuume?.(target.text)
  }
  // `by_employee` covers the week's costed rows. Someone the review touches
  // who is not in it costs nothing — that is $0, not missing payroll data.
  // Only the server's own unpriced list means "no rate on file"; conflating
  // them sends a manager hunting for a data problem that does not exist.
  const unpricedIds = new Set(review.cost?.unpriced_employee_ids ?? [])
  const personCost = (employeeId: string, side: 'before' | 'after') => {
    if (!review.cost) return undefined
    if (unpricedIds.has(employeeId)) return null
    return review.cost.by_employee[employeeId]?.[side] ?? 0
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto" aria-label="Review">
      <header className="px-4 pt-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className={LABEL}>{KIND_LABEL[review.kind] ?? 'Review'}</div>
            <h2 className="mt-0.5 truncate text-base font-semibold tracking-tight text-zinc-100">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[11px] text-zinc-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </div>
        <ApprovalVerdict
          verdict={verdict}
          onFix={fix}
          onShowWeek={review.kind === 'week_draft' ? onShowWeek : undefined}
          onApprove={onApprove}
          onCancel={onCancel}
          decisionDisabled={decisionDisabled}
        />
        {review.cost && (
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[11px]">
            <span className="font-mono tabular-nums text-zinc-500">
              {costLabel(review.cost.before)} <ArrowRight className="inline h-3 w-3 text-zinc-600" /> <span className="text-zinc-200">{costLabel(review.cost.after)}</span>
            </span>
            <span className={`font-mono tabular-nums font-medium ${review.cost.delta > 0 ? 'text-amber-300' : review.cost.delta < 0 ? 'text-emerald-300' : 'text-zinc-400'}`}>
              {costDeltaLabel(review.cost.delta)}
            </span>
            {review.cost.ot_premium_after > review.cost.ot_premium_before && (
              <span className="text-amber-300/90" title="What the overtime hours cost above their own base rate">
                {costDeltaLabel(review.cost.ot_premium_after - review.cost.ot_premium_before)} of it overtime
              </span>
            )}
            {review.cost.unpriced_employee_count > 0 && (
              <span className="text-zinc-600">
                {review.cost.unpriced_employee_count} unpriced (no rate on file)
              </span>
            )}
            <span className="text-zinc-700">scheduled, not worked</span>
          </div>
        )}
        <div className={`mt-3 rounded-lg border px-3 py-2 text-[11px] leading-snug ${tone.className}`} role="status">
          <span className="font-medium">{tone.label}.</span> {review.jurisdiction.message}
        </div>
      </header>

      {review.demand_model && <DemandModelBlock model={review.demand_model} open={evidenceOpen} />}

      {diff && compare ? (
        <>
          <section className="mt-3 border-t border-white/[0.06] px-4 py-3">
            <div className="mb-2 flex items-center gap-2">
              <span className={LABEL}>Compared with</span>
              <span className="text-xs text-zinc-200">{compare.label}</span>
              <span className="ml-auto font-mono text-[10px] tabular-nums text-zinc-500">
                {diff.totals.left.staged}/{diff.totals.left.unfilled} vs {diff.totals.right.staged}/{diff.totals.right.unfilled} staged/unfilled
              </span>
            </div>
            {diff.cost && (
              <p className="mb-2 font-mono text-[11px] tabular-nums text-zinc-400">
                {costLabel(diff.cost.left)} vs {costLabel(diff.cost.right)}
                <span className={`ml-2 font-medium ${diff.cost.delta > 0 ? 'text-amber-300' : diff.cost.delta < 0 ? 'text-emerald-300' : 'text-zinc-500'}`}>
                  {costDeltaLabel(diff.cost.delta)}
                </span>
              </p>
            )}
            {diff.assignments.length === 0 ? (
              <p className="text-xs text-zinc-500">Both scenarios staff every shift the same way.</p>
            ) : (
              <ul className="divide-y divide-white/[0.04]">
                {diff.assignments.map((row) => (
                  <li key={row.shift_id} className="group flex items-center gap-3 py-1.5 text-xs">
                    <span className="w-40 shrink-0 truncate text-zinc-400">{row.role} · {when(row.starts_at, null)}</span>
                    <span className={`min-w-0 flex-1 truncate ${row.left ? 'text-zinc-200' : 'text-zinc-600 italic'}`}>{row.left ?? 'open'}</span>
                    <ArrowRight className="h-3 w-3 shrink-0 text-zinc-600" />
                    <span className={`min-w-0 flex-1 truncate ${row.right ? 'text-emerald-200' : 'text-zinc-600 italic'}`}>{row.right ?? 'open'}</span>
                    <RowActions shiftId={row.shift_id} onShowShift={onShowShift} />
                  </li>
                ))}
              </ul>
            )}
          </section>
          <Block label="Hours after each" count={diff.employees.length}>
            <ul className="space-y-1.5">
              {diff.employees.map((person) => (
                <li key={person.employee_id} className="flex items-center gap-3 text-xs">
                  <span className="w-32 shrink-0 truncate text-zinc-200">{person.name}</span>
                  <span className="font-mono tabular-nums text-zinc-300">{hoursLabel(person.left)}</span>
                  <ArrowRight className="h-3 w-3 text-zinc-600" />
                  <span className={`font-mono tabular-nums ${person.right > person.left ? 'text-emerald-300' : person.right < person.left ? 'text-red-300' : 'text-zinc-300'}`}>{hoursLabel(person.right)}</span>
                </li>
              ))}
            </ul>
          </Block>
        </>
      ) : (
        <>
          <Block open={evidenceOpen} label="Load" count={review.employees.length}>
            <ul className="space-y-2.5">
              {review.employees.map((person) => (
                <li key={person.employee_id} className="group">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="min-w-0 flex-1 truncate text-zinc-200">{person.name}</span>
                    <span className="font-mono text-[10px] tabular-nums text-zinc-500">
                      {person.before.shifts ?? 0}→{person.after.shifts ?? 0} shifts · {person.before.days ?? 0}→{person.after.days ?? 0} days
                    </span>
                    <RowActions ask={askAbout('employee', { name: person.name })} onAskHuume={onAskHuume} />
                  </div>
                  <div className="mt-1">
                    <LoadBar
                      name={person.name}
                      minutes={person.before.minutes ?? 0}
                      afterMinutes={person.after.minutes ?? 0}
                      capMinutes={caps?.[person.employee_id]?.max_weekly_minutes ?? null}
                      allowOvertime={caps?.[person.employee_id]?.allow_overtime ?? false}
                      policyMinutes={policyMinutes}
                      cost={personCost(person.employee_id, 'before')}
                      afterCost={personCost(person.employee_id, 'after')}
                    />
                  </div>
                  {person.warnings.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {person.warnings.map((warning) => (
                        <li key={warning} className="flex items-start gap-1.5 text-[11px] text-amber-300"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{warning}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </Block>

          <Block open={evidenceOpen} label="Staged" count={staged.length}>
            <ul className="divide-y divide-white/[0.04]">
              {staged.map((item, index) => (
                <li key={`${item.shift_id}-${item.employee_id}-${index}`} className="group py-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    {item.verdict === 'warn' ? <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" /> : <CircleCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />}
                    <span className="font-mono text-[10px] uppercase tracking-wide text-zinc-500">{item.op}</span>
                    <span className="min-w-0 flex-1 truncate text-zinc-200">
                      {item.employee_name ?? <span className="italic text-zinc-500">open</span>} <span className="text-zinc-500">· {item.role} · {when(item.starts_at, item.ends_at)}</span>
                    </span>
                    <RowActions shiftId={item.shift_id} ask={askAbout('assignment', { name: item.employee_name, role: item.role, when: when(item.starts_at, item.ends_at) })} onShowShift={onShowShift} onAskHuume={onAskHuume} />
                  </div>
                  {item.reasons.length > 0 && (
                    <ul className="ml-5 mt-0.5 space-y-0.5 text-[11px] text-amber-300">
                      {item.reasons.map((reason) => <li key={reason.code + reason.message}>{reason.message}{reason.policy ? ' (policy)' : ''}</li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </Block>

          <Block open={evidenceOpen} label="Not staged" count={review.rejected.length} tone="bad">
            <ul className="divide-y divide-white/[0.04]">
              {review.rejected.map((item, index) => (
                <li key={`${item.shift_id}-${index}`} className="group py-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <CircleSlash className="h-3.5 w-3.5 shrink-0 text-red-400" />
                    <span className="min-w-0 flex-1 truncate text-zinc-200">{item.employee_name ?? 'Someone'} <span className="text-zinc-500">· {item.role} · {when(item.starts_at, item.ends_at)}</span></span>
                    <RowActions shiftId={item.shift_id} ask={askAbout('rejected', { name: item.employee_name, role: item.role, when: when(item.starts_at, item.ends_at), reason: item.reasons[0]?.message })} onShowShift={onShowShift} onAskHuume={onAskHuume} />
                  </div>
                  <ul className="ml-5 mt-0.5 space-y-0.5 text-[11px] text-red-300/90">
                    {item.reasons.map((reason) => <li key={reason.code + reason.message}>{reason.message}</li>)}
                  </ul>
                </li>
              ))}
            </ul>
          </Block>

          <Block open={evidenceOpen} label="Unfilled" count={review.unfilled.length} tone="warn">
            <ul className="divide-y divide-white/[0.04]">
              {review.unfilled.map((item) => (
                <li key={item.shift_id} className="group py-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="h-3.5 w-3.5 shrink-0 rounded-sm border border-dashed border-amber-400/70" aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-zinc-200">{item.role || 'Shift'} <span className="text-zinc-500">· {when(item.starts_at, item.ends_at)}</span></span>
                    <RowActions shiftId={item.shift_id} ask={askAbout('unfilled', { role: item.role, when: when(item.starts_at, item.ends_at), reason: item.reason })} onShowShift={onShowShift} onAskHuume={onAskHuume} />
                  </div>
                  <p className="ml-5 mt-0.5 text-[11px] text-amber-300/90">
                    {item.reason}
                    {Object.keys(item.exclusions).length > 1 && (
                      <span className="text-zinc-500"> · {Object.entries(item.exclusions).map(([reason, count]) => `${count} ${reason}`).join(', ')}</span>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          </Block>

          <Block open={evidenceOpen} label="Statutory advisories" count={review.advisories.length} tone="warn">
            <ul className="space-y-1.5 text-[11px] text-zinc-300">
              {review.advisories.map((item, index) => (
                <li key={index} className="leading-snug">
                  {item.employee_name && <span className="text-zinc-100">{item.employee_name}: </span>}
                  {item.message}
                  {item.statute && <span className="text-zinc-500"> ({item.statute})</span>}
                </li>
              ))}
            </ul>
          </Block>

          <Block open={evidenceOpen} label="Findings" count={review.findings.length}>
            {/* One line per KIND with its count — 28 identical sentences are
                one fact. The distinct details stay one click away. */}
            <ul className="space-y-1.5 text-[11px]" aria-label="Findings by kind">
              {findingGroups.map((group) => (
                <li key={`${group.severity}:${group.kind}`} className="leading-snug text-zinc-300">
                  <details>
                    <summary className="flex cursor-pointer list-none items-start gap-2 [&::-webkit-details-marker]:hidden">
                      <span className={`mt-0.5 shrink-0 rounded px-1 font-mono text-[9px] uppercase ${group.severity === 'gap' ? 'bg-red-500/15 text-red-300' : 'bg-amber-500/15 text-amber-300'}`}>{group.severity}</span>
                      <span><span className="font-mono tabular-nums text-zinc-100">{group.count}</span> × {group.label}</span>
                    </summary>
                    <ul className="ml-10 mt-1 list-disc space-y-0.5 text-zinc-500">
                      {group.details.slice(0, 6).map((detail) => <li key={detail}>{detail}</li>)}
                      {group.details.length > 6 && <li className="list-none">+{group.details.length - 6} more like these</li>}
                    </ul>
                  </details>
                </li>
              ))}
            </ul>
          </Block>
        </>
      )}
    </div>
  )
}
