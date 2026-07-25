import { motion, AnimatePresence } from 'framer-motion'
import { Modal } from '../../ui/Modal'
import type { RequirementComponentChecklist, RequirementComponentSummary, RiskPenalty } from '../../../types/compliance'
import { STATUS_LABEL, STATUS_CLASS, STATUS_GLYPH } from './componentStatus'
import { useAuditReveal, weighingSteps } from './useAuditReveal'

type Props = {
  open: boolean
  onClose: () => void
  checklist: RequirementComponentChecklist
  employeeCount?: number | null
  runId: number
}

/** The statutory-penalty line, worded by what has actually been established.
 *  `penalty` is a statutory CEILING, not a finding — printing "Exposure" on
 *  it while every clause is still `unknown` presents a hypothetical as a
 *  liability, exactly what compliance_risk.py's separate `conditional_ceiling`
 *  field (never added to confirmed exposure) exists to avoid. Only a real
 *  `non_compliant` clause earns the "Exposure" wording; otherwise it reads as
 *  the conditional ceiling it is. */
export function exposureLabel(
  summary: RequirementComponentSummary,
  penalty: RiskPenalty | null,
): string | null {
  if (!penalty) return null
  const prefix = summary.count_non_compliant > 0 ? 'Exposure' : 'If unproven,'
  const amount = penalty.civil_max != null ? ` up to $${penalty.civil_max.toLocaleString()}` : ''
  const agency = penalty.enforcing_agency ? ` · ${penalty.enforcing_agency}` : ''
  return `${prefix}${amount}${agency} · directional`
}

function lastActivity(checklist: RequirementComponentChecklist): string {
  const stamps = checklist.components
    .flatMap((c) => [c.derived_at, c.attested_at])
    .filter((s): s is string => !!s)
  if (stamps.length === 0) return 'never'
  const latest = stamps.reduce((a, b) => (a > b ? a : b))
  return new Date(latest).toLocaleDateString()
}

export function AuditRevealModal({ open, onClose, checklist, employeeCount, runId }: Props) {
  const { phase, states, hud, skip } = useAuditReveal(checklist.components, { active: open, runId })
  const n = checklist.components.length
  const { summary } = checklist
  const exposureText = exposureLabel(summary, checklist.exposure?.penalty ?? null)

  return (
    <Modal open={open} onClose={onClose} bare dismissible>
      <div
        className="w-full max-w-6xl max-h-[85vh] overflow-y-auto rounded-2xl border border-white/10 bg-zinc-950 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header card — real numbers, not a scripted scenario */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: phase === 'idle' ? 0 : 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="rounded-lg border border-amber-800/30 bg-white/[0.02] px-5 py-4 mb-8"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" style={{ boxShadow: '0 0 6px #d7ba7d' }} />
                <span className="font-mono text-xs font-semibold uppercase tracking-wide text-zinc-200">
                  {checklist.title}
                </span>
              </div>
              <p className="text-[11px] text-zinc-500 mt-1">
                {checklist.statute_citation} · {employeeCount ?? '—'} employees · last activity: {lastActivity(checklist)}
              </p>
              {exposureText && (
                <p className="text-[11px] text-amber-400/80 mt-1">{exposureText}</p>
              )}
            </div>
            <div className="text-right shrink-0">
              <div className="font-mono text-lg font-bold text-amber-300 tabular-nums">
                {summary.known}/{summary.total}
              </div>
              <div className="text-[10px] text-zinc-500 uppercase tracking-wide">known</div>
            </div>
          </div>
        </motion.div>

        {/* Root node */}
        <AnimatePresence>
          {phase !== 'idle' && phase !== 'header' && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-center mb-6"
            >
              <div className="rounded-md px-3.5 py-2 flex items-center gap-2 border border-amber-800/30 bg-white/[0.03]">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                <span className="font-mono text-[10px] font-semibold uppercase tracking-wide text-zinc-200">
                  {checklist.title.length > 40 ? 'Statute audit' : checklist.title}
                </span>
                <span className="font-mono text-[9px] text-zinc-600">·</span>
                <span className="font-mono text-[9px] text-zinc-500">{n} components</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Fan connector + columns */}
        <div className="relative overflow-x-auto">
          <div className="min-w-fit">
            <svg className="absolute inset-0 w-full pointer-events-none" style={{ top: -24, height: 40 }} preserveAspectRatio="none">
              {checklist.components.map((_, i) => {
                const xPct = ((i + 0.5) / n) * 100
                const isActive = states[i]?.phase !== 'pending'
                return (
                  <motion.line
                    key={i}
                    x1="50%" y1="0" x2={`${xPct}%`} y2="40"
                    stroke={isActive ? '#d7ba7d' : 'rgba(255,255,255,0.1)'}
                    strokeWidth={isActive ? 1 : 0.7}
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: phase === 'fanning' || phase === 'done' ? 1 : 0, opacity: phase === 'idle' || phase === 'header' ? 0 : 1 }}
                    transition={{ duration: 0.5, delay: i * 0.08 }}
                  />
                )
              })}
            </svg>
            <div
              className="grid gap-3 pt-4"
              style={{ gridTemplateColumns: `repeat(${n}, minmax(160px, 1fr))` }}
            >
              {checklist.components.map((c, i) => {
                const state = states[i] ?? { phase: 'pending' as const, weighIdx: 0 }
                const isPending = state.phase === 'pending'
                const isWeighing = state.phase === 'weighing'
                const isCommitted = state.phase === 'committed' || state.phase === 'remediated'
                const showFix = state.phase === 'remediated'
                const steps = weighingSteps(c)
                const accent = c.status === 'compliant' ? '#34d399'
                  : c.status === 'non_compliant' ? '#f87171'
                  : c.status === 'in_progress' ? '#d7ba7d'
                  : '#8b8f96'

                return (
                  <div key={c.component_key} className="flex flex-col items-center gap-1.5">
                    <div className="h-4 flex items-center justify-center w-full">
                      <AnimatePresence>
                        {isWeighing && (
                          <motion.div
                            key="weighing"
                            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            className="font-mono text-[8px] tabular-nums text-amber-400/80"
                          >
                            {steps[state.weighIdx]}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>

                    <motion.div
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: isPending ? 0.3 : 1, y: 0, scale: isWeighing ? 1.04 : 1 }}
                      transition={{ duration: 0.35, delay: i * 0.06 }}
                      className="rounded-md w-full px-2.5 py-2 text-center border"
                      style={{
                        backgroundColor: 'rgba(20,20,16,0.85)',
                        borderColor: isCommitted ? `${accent}40` : isWeighing ? '#d7ba7d40' : 'rgba(255,255,255,0.07)',
                        boxShadow: isWeighing ? '0 0 8px #d7ba7d16' : isCommitted ? `0 0 8px ${accent}16` : 'none',
                      }}
                    >
                      <div className="font-mono text-[9px] uppercase tracking-wider text-zinc-300">{c.label}</div>
                      {isCommitted && c.statute_citation && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="font-mono text-[8.5px] mt-0.5" style={{ color: accent }}>
                          {c.statute_citation}
                        </motion.div>
                      )}
                    </motion.div>

                    <AnimatePresence>
                      {isCommitted && (
                        <motion.div
                          initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                          transition={{ type: 'spring', stiffness: 380, damping: 22 }}
                          className={`rounded-full px-2 py-[2px] font-mono text-[9px] font-bold tracking-wider uppercase flex items-center gap-1 border ${STATUS_CLASS[c.status]}`}
                        >
                          <span>{STATUS_GLYPH[c.status]}</span>
                          <span>{STATUS_LABEL[c.status]}</span>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <AnimatePresence>
                      {isCommitted && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                          className="font-mono text-[8px] italic text-center px-1 text-zinc-600"
                        >
                          "{c.question}"
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <AnimatePresence>
                      {showFix && c.status !== 'compliant' && c.suggested_fix && (
                        <motion.div
                          initial={{ opacity: 0, y: -6, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0 }}
                          transition={{ duration: 0.32, ease: 'easeOut' }}
                          className="rounded-md w-full px-2.5 py-2 text-center mt-1 border border-emerald-800/30 bg-white/[0.02]"
                        >
                          <div className="font-mono text-[7.5px] uppercase tracking-wider mb-0.5 text-emerald-400">
                            Suggested fix
                          </div>
                          <div className="font-mono text-[9px] leading-tight text-zinc-300">{c.suggested_fix}</div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* HUD footer */}
        <div className="flex items-center justify-between mt-8 pt-3 border-t border-white/[0.06]">
          <span className="font-mono text-[10px] text-zinc-500">
            Status <span className="text-zinc-300">{hud}</span>
          </span>
          <div className="flex items-center gap-3">
            {phase !== 'done' && (
              <button
                type="button"
                onClick={skip}
                className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                Skip
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="text-[11px] px-3 py-1 rounded border border-white/10 text-zinc-300 hover:bg-white/[0.04] transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
