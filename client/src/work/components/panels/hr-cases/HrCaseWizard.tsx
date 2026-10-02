import { useEffect, useRef, useState } from 'react'
import { Bell, ChevronLeft, ChevronRight, Columns3, Flag, Hand, ShieldCheck, X } from 'lucide-react'
import type { HrCaseColumn, HrCaseReadiness } from '../../../types'
import SetupCheck from './SetupCheck'
import { COLUMN_GUIDE, NEEDS_YOU_MOMENTS, triggers } from './hrCaseGuide'

export const HR_CASES_GUIDE_SEEN_KEY = 'hr-cases-guide-seen'

type Props = {
  columns: HrCaseColumn[]
  readiness: HrCaseReadiness | null
  readinessLoading: boolean
  readinessError: boolean
  onClose: () => void
}

const STEPS = [
  { title: 'What opens a case', icon: Flag },
  { title: 'Where a case goes', icon: Columns3 },
  { title: 'When it needs you', icon: Hand },
  { title: 'How you’ll hear about it', icon: Bell },
  { title: 'Is everything set up?', icon: ShieldCheck },
] as const

export default function HrCaseWizard({ columns, readiness, readinessLoading, readinessError, onClose }: Props) {
  const [step, setStep] = useState(0)
  const last = step === STEPS.length - 1
  const Icon = STEPS[step].icon
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    dialogRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 sm:items-center sm:px-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="How HR cases work"
        className="flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-t-2xl border border-w-line bg-w-surface shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-w-line px-5 py-4 sm:px-6">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-w-accent">How HR cases work</p>
            <p className="mt-1 text-xs text-w-dim">Step {step + 1} of {STEPS.length}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-w-text" aria-label="Close">
            <X size={17} />
          </button>
        </div>

        <div className="flex gap-1.5 px-5 pt-4 sm:px-6" aria-hidden>
          {STEPS.map((s, i) => <span key={s.title} className={`h-1.5 rounded-full transition-all ${i === step ? 'w-8 bg-w-accent' : i < step ? 'w-1.5 bg-w-accent' : 'w-1.5 bg-w-surface2'}`} />)}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-6">
          <div className="mb-4 flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-w-line bg-w-surface2/70"><Icon size={18} className="text-w-accent" /></span>
            <h2 className="text-lg font-semibold text-w-text">{STEPS[step].title}</h2>
          </div>

          {step === 0 && (
            <div className="space-y-2">
              <p className="mb-3 text-sm leading-6 text-w-dim">You don’t open cases by hand. They start on their own, three ways:</p>
              {triggers(readiness?.threshold).map((t, i) => (
                <div key={t.title} className="flex gap-3 rounded-lg border border-w-line bg-w-surface2/40 p-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-w-accent/15 text-[11px] font-semibold text-w-accent">{i + 1}</span>
                  <div><p className="text-sm font-medium text-w-text">{t.title}</p><p className="mt-0.5 text-xs leading-5 text-w-dim">{t.body}</p></div>
                </div>
              ))}
              <p className="pt-2 text-xs leading-5 text-w-faint">No handbook or policy content means nothing can be flagged. The last step checks that.</p>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-2">
              <p className="mb-3 text-sm leading-6 text-w-dim">A case moves left to right. “Acts” is who has the next move.</p>
              {columns.map((col) => {
                const g = COLUMN_GUIDE[col.key]
                return (
                  <div key={col.key} className="rounded-lg border border-w-line bg-w-surface2/40 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-w-text">{col.label}</p>
                      {g && <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${g.acts === 'You' ? 'bg-w-accent/15 text-w-accent' : 'bg-w-surface2 text-w-dim'}`}>Acts: {g.acts}</span>}
                    </div>
                    {g && <p className="mt-1 text-xs leading-5 text-w-dim">{g.lands}</p>}
                  </div>
                )
              })}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-2">
              <p className="mb-3 text-sm leading-6 text-w-dim">Most of a case runs without you. Three moments are yours:</p>
              {NEEDS_YOU_MOMENTS.map((m) => (
                <div key={m.title} className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-3">
                  <p className="text-sm font-medium text-w-text">{m.title}</p>
                  <p className="mt-0.5 text-xs leading-5 text-w-dim">{m.body}</p>
                </div>
              ))}
              <p className="pt-2 text-xs leading-5 text-w-faint">Managers never see the leave findings or the handbook matches. You decide; nothing is approved or sent without a person.</p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <p className="text-sm leading-6 text-w-dim">Each of those moments sends you a notice, so an empty board never means you’ve missed something.</p>
              <ul className="space-y-2 text-xs leading-5 text-w-dim">
                <li className="rounded-lg border border-w-line bg-w-surface2/40 p-3"><span className="font-medium text-w-text">Bell and email.</span> The same notice lands in both. The bell is in the top bar on every page.</li>
                <li className="rounded-lg border border-w-line bg-w-surface2/40 p-3"><span className="font-medium text-w-text">Updates, on this page.</span> The Updates button lists just HR cases, marks what’s new, and refreshes the board when something changes while you’re here.</li>
                <li className="rounded-lg border border-w-line bg-w-surface2/40 p-3"><span className="font-medium text-w-text">Waiting on you.</span> When a case needs a decision, a strip at the top of the board says so and opens it.</li>
              </ul>
              <p className="text-xs leading-5 text-w-faint">Notices carry the case and incident numbers and the policy titles, never the incident narrative.</p>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-3">
              <p className="text-sm leading-6 text-w-dim">For a new incident to open a case, these need to be true:</p>
              <SetupCheck readiness={readiness} loading={readinessLoading} error={readinessError} />
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-w-line px-5 py-4 sm:px-6">
          {step > 0
            ? <button type="button" onClick={() => setStep((s) => s - 1)} className="inline-flex items-center gap-1 text-sm text-w-dim hover:text-w-text"><ChevronLeft size={16} />Back</button>
            : <button type="button" onClick={onClose} className="text-sm text-w-dim hover:text-w-text">Skip</button>}
          {last
            ? <button type="button" onClick={onClose} className="rounded-lg bg-w-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi">Got it</button>
            : <button type="button" onClick={() => setStep((s) => s + 1)} className="inline-flex items-center gap-1 rounded-lg bg-w-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi">Next <ChevronRight size={16} /></button>}
        </div>
      </div>
    </div>
  )
}
