import { useState } from 'react'
import { Info, X } from 'lucide-react'

// ── One-time "how this works" guide (collapses to a reopenable link) ──
const GUIDE_KEY = 'compliance_cockpit_guide_dismissed'

export function GuideBanner() {
  // Collapsed by default. This is a four-bullet manual, and it was opening
  // itself above the fold on a page people work in every day — pushing the
  // action queue, the thing they came for, off the screen. Every element it
  // describes already carries its own (?) hint, so the explanation is here for
  // whoever wants it rather than in front of everyone who doesn't.
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(GUIDE_KEY) === '1' } catch { return false }
  })
  function set(next: boolean) {
    setOpen(next)
    try { localStorage.setItem(GUIDE_KEY, next ? '1' : '0') } catch { /* ignore */ }
  }
  const close = () => set(false)

  if (!open) {
    return (
      <button type="button" onClick={() => set(true)}
        className="inline-flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
        <Info className="h-3.5 w-3.5" /> How this page works
      </button>
    )
  }
  return (
    <div className="rounded-lg border border-white/[0.08] bg-zinc-900/40 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <Info className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="text-xs text-zinc-300 space-y-1.5">
            <p className="text-zinc-100 font-medium">Your compliance risk at a glance — and how to clear it.</p>
            <ul className="space-y-1 text-zinc-400">
              <li>• The <b className="text-zinc-200">strip</b> up top measures where you stand: open issues by urgency, the estimated penalty exposure, who's affected, and your next deadline. Hover any <span className="text-zinc-300">(?)</span> for detail.</li>
              <li>• The <b className="text-zinc-200">Action queue</b> is your to-do list, worst first. Hit <span className="text-emerald-300">Fix</span> to jump to the exact record and correct it — the issue then clears itself.</li>
              <li>• Every fix is written to <b className="text-zinc-200">Remediation history</b> automatically (who, when, how) — your paper trail for audits and claims.</li>
              <li>• Not a real violation? <span className="text-zinc-300">Dismiss</span> it with a reason. It comes back on its own if the numbers change.</li>
            </ul>
          </div>
        </div>
        <button type="button" onClick={close} aria-label="Dismiss guide"
          className="shrink-0 text-zinc-500 hover:text-zinc-200 transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
