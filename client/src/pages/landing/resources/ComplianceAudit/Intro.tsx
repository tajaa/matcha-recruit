import { ArrowRight } from 'lucide-react'

import type { Theme } from './theme'

export function Intro({ t, embedded, onStart }: { t: Theme; embedded?: boolean; onStart: () => void }) {
  return (
    <>
      <header className="mb-10">
        <h1
          className={embedded ? "text-2xl font-semibold text-vsc-text" : "text-5xl sm:text-6xl tracking-tight"}
          style={embedded ? undefined : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
        >
          12-Question HR Compliance Audit
        </h1>
        <p className={`mt-4 text-base ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
          A 3-minute self-audit covering the highest-cost compliance
          areas: posters, handbooks, I-9s, classification, leave,
          harassment, records, terminations, background checks, pay
          transparency, and lactation accommodation.
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-10">
        {[
          { n: '12', l: 'questions' },
          { n: '~3', l: 'minutes' },
          { n: 'PDF', l: 'gap report emailed' },
        ].map(s => (
          <div
            key={s.l}
            className={`p-5 rounded-xl text-center ${embedded ? 'border border-vsc-border bg-vsc-panel' : ''}`}
            style={embedded ? undefined : { border: `1px solid ${t.line}` }}
          >
            <div className={`text-3xl mb-1 ${embedded ? 'text-vsc-text font-semibold' : ''}`} style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}>{s.n}</div>
            <div className={`text-xs ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>{s.l}</div>
          </div>
        ))}
      </div>

      <button
        onClick={onStart}
        className={`w-full sm:w-auto inline-flex items-center justify-center gap-2 ${embedded ? 'h-9 px-4 rounded-lg text-xs font-medium bg-zinc-700 hover:bg-zinc-600 text-white transition-colors' : 'px-6 h-12 rounded-full text-sm font-medium'}`}
        style={embedded ? undefined : t.btnPrimary}
      >
        Start the audit <ArrowRight className="w-4 h-4" />
      </button>

      <p className={`text-xs mt-6 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
        Responses stay in your browser. Email yourself the gap report
        from the results screen. Informational only — not legal advice.
      </p>
    </>
  )
}
