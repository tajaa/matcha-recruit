import { ArrowLeft, ArrowRight } from 'lucide-react'

import { INDUSTRIES } from '../auditRules'
import { STATES_50 } from './constants'
import type { Theme } from './theme'

export function Context(props: {
  t: Theme
  embedded?: boolean
  stateSlug: string; setStateSlug: (s: string) => void
  headcount: number | ''; setHeadcount: (n: number | '') => void
  industry: string; setIndustry: (s: string) => void
  onBack: () => void; onNext: () => void
}) {
  const { t, embedded } = props
  return (
    <>
      <header className="mb-8">
        <p className={`text-xs uppercase tracking-wider mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Step 1 of 2</p>
        <h2
          className={embedded ? 'text-xl font-semibold text-vsc-text' : 'text-3xl'}
          style={embedded ? undefined : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
        >
          Tell us about your business
        </h2>
        <p className={`mt-2 text-sm ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
          Used to tailor your gap report. Not stored unless you email yourself the results.
        </p>
      </header>

      <div className="flex flex-col gap-5 mb-10">
        <div>
          <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Primary state</label>
          <select
            value={props.stateSlug}
            onChange={e => props.setStateSlug(e.target.value)}
            className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
            style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
          >
            <option value="">— Select state —</option>
            {STATES_50.map(s => (
              <option key={s.slug} value={s.slug}>{s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Headcount (US employees)</label>
          <input
            type="number"
            min={1}
            value={props.headcount}
            onChange={e => props.setHeadcount(e.target.value ? Number(e.target.value) : '')}
            className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
            style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
          />
        </div>
        <div>
          <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Industry</label>
          <select
            value={props.industry}
            onChange={e => props.setIndustry(e.target.value)}
            className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
            style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
          >
            {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <button
          onClick={props.onBack}
          className={`inline-flex items-center gap-2 text-sm transition-colors ${embedded ? 'text-vsc-text/50 hover:text-vsc-text' : 'transition-opacity hover:opacity-60'}`}
          style={embedded ? undefined : { color: t.ink }}
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <button
          onClick={props.onNext}
          className={`inline-flex items-center gap-2 font-medium ${embedded ? 'h-9 px-4 rounded-lg text-xs bg-zinc-700 hover:bg-zinc-600 text-white transition-colors' : 'px-6 h-11 rounded-full text-sm'}`}
          style={embedded ? undefined : t.btnPrimary}
        >
          Continue <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </>
  )
}
