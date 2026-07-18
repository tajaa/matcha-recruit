import { useState } from 'react'
import {
  ArrowLeft, ArrowRight, Building2, FileText, FileUp, Handshake, MessageSquareQuote, Sparkles, X,
} from 'lucide-react'
import { LABEL } from './shared'

const STEPS = [
  {
    icon: Building2,
    title: 'Start a session on a client',
    body: 'Pick any client from your book — an on-platform Matcha client or an external one you track '
      + 'in the External Book — then pick a mode. Each mode names the documents it analyzes up front, '
      + 'and asks you for the ones this client doesn’t already have on file.',
    detail: 'A mode never asks twice: a contract already read on the client’s Limits tab, or loss history '
      + 'already on the platform, counts as provided.',
  },
  {
    icon: Sparkles,
    title: 'The record assembles itself',
    body: 'The systems strip across the top shows everything in scope: the analytics you’ve entered '
      + '(loss runs, WC, EPL, property), the indemnity clauses read out of the client’s contracts, plus — '
      + 'for on-platform clients — the operational records Matcha generates natively: incidents, ER cases, '
      + 'compliance, discipline, training, policy acknowledgments.',
    detail: 'Dark systems on the strip mean no data yet — for external clients, they light up once the client operates on Matcha.',
  },
  {
    icon: Handshake,
    title: 'Review a contract before your client signs',
    body: 'On the client’s Limits tab, upload a lease, subcontract, or vendor agreement. We extract the '
      + 'insurance the counterparty requires — limits, additional insured, waiver of subrogation, primary '
      + '& non-contributory — and the indemnification clause, then diff it all against what the client carries.',
    detail: 'You get a compliant / exposed / actions summary plus a client-ready PDF. Insurance and risk-transfer '
      + 'provisions only — it is not legal advice, and every page says so.',
  },
  {
    icon: FileUp,
    title: 'Add carrier documents',
    body: 'Upload loss runs, dec pages, competing quotes, carrier letters, or contracts (PDF/DOCX/TXT/CSV). '
      + 'Each is analyzed once — key figures are extracted — and grounds every answer from then on. The '
      + 'Documents panel tracks which of the mode’s documents are still outstanding.',
    detail: 'When a document disagrees with the platform data, the analyst says so and cites both sides. Ask '
      + 'before a document lands and it tells you plainly what it is working without.',
  },
  {
    icon: MessageSquareQuote,
    title: 'Ask the analyst — everything is cited',
    body: 'Ask what the record shows. Every answer is grounded: each observation carries citations to the '
      + 'exact records behind it, and anything the record does not establish lands under open questions.',
    detail: 'Ungrounded claims are removed by a citation check before you see them — no invented figures.',
  },
  {
    icon: FileText,
    title: 'Export a professional memo',
    body: 'One click renders the analysis as a client-ready PDF: narrative, numbered grounded observations, '
      + 'an evidence index, and appendices reproducing every cited record and document extraction.',
    detail: 'Memos are stored under Work product in the right panel, ready to re-download any time.',
  },
]

export function HowItWorksModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0)
  const s = STEPS[step]
  const Icon = s.icon

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-white/[0.08] bg-zinc-950"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
          <span className={LABEL}>How Broker Pilot works</span>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.04] hover:text-zinc-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-6">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06]">
              <Icon className="h-4.5 w-4.5 text-emerald-400" />
            </span>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">Step {step + 1} of {STEPS.length}</div>
              <h3 className="text-[15px] font-semibold text-zinc-100">{s.title}</h3>
            </div>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-zinc-300">{s.body}</p>
          <p className="mt-2.5 border-l-2 border-emerald-500/30 pl-3 text-[13px] leading-relaxed text-zinc-500">{s.detail}</p>
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-3">
          <div className="flex items-center gap-1.5">
            {STEPS.map((_, i) => (
              <button key={i} onClick={() => setStep(i)} aria-label={`Step ${i + 1}`}
                className={`h-1.5 rounded-full transition-all ${i === step ? 'w-5 bg-emerald-400' : 'w-1.5 bg-zinc-700 hover:bg-zinc-600'}`} />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button onClick={() => setStep(step - 1)}
                className="inline-flex items-center gap-1 rounded border border-white/[0.08] px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:text-zinc-100">
                <ArrowLeft className="h-3 w-3" /> Back
              </button>
            )}
            {step < STEPS.length - 1 ? (
              <button onClick={() => setStep(step + 1)}
                className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-500">
                Next <ArrowRight className="h-3 w-3" />
              </button>
            ) : (
              <button onClick={onClose}
                className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-500">
                Got it
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
