import { useRef, useState, useEffect } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'

const INCIDENTS = [
  { id: 'INC-1042', loc: 'Atlanta — Store 7', type: 'Behavioral', sev: 'High', when: '2h ago', status: 'open' },
  { id: 'INC-1041', loc: 'Phoenix — Warehouse', type: 'Safety', sev: 'Med', when: '5h ago', status: 'review' },
  { id: 'INC-1040', loc: 'Denver — HQ', type: 'Property', sev: 'Low', when: '1d ago', status: 'closed' },
  { id: 'INC-1039', loc: 'Seattle — Store 12', type: 'Behavioral', sev: 'Med', when: '2d ago', status: 'closed' },
]

const RISK_LOCATIONS = [
  { name: 'Atlanta — Store 7', score: 78, count: 6, trend: 'up' },
  { name: 'Phoenix — Warehouse', score: 54, count: 4, trend: 'flat' },
  { name: 'Denver — HQ', score: 22, count: 1, trend: 'down' },
  { name: 'Seattle — Store 12', score: 41, count: 3, trend: 'flat' },
]

const fade = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -4 } }

export function MatchaLiteMockup() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-60px' })
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (!inView) { setStep(0); return }
    const timers = [
      setTimeout(() => setStep(1), 600),
      setTimeout(() => setStep(2), 2400),
      setTimeout(() => setStep(3), 4400),
    ]
    return () => timers.forEach(clearTimeout)
  }, [inView])

  return (
    <div ref={ref} className="relative w-full max-w-5xl mx-auto rounded-xl overflow-hidden border border-zinc-700/50 bg-zinc-950 shadow-2xl flex flex-col md:flex-row h-[520px] font-sans">

      {/* Sidebar */}
      <div className="hidden md:flex flex-col w-56 border-r border-zinc-800/50 bg-zinc-900/40 p-4">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
          <span className="text-[11px] font-bold tracking-widest text-zinc-200 uppercase">Matcha Lite</span>
        </div>

        <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Risk + Safety</div>
        <div className="flex flex-col gap-1">
          <div className="px-3 py-2 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>
            Incidents
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
            Trends
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
            Employees
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            Locations
          </div>
        </div>

        <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mt-5 mb-2">Resources</div>
        <div className="flex flex-col gap-1">
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Templates
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="6" x2="15" y2="6"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="13" y2="14"/></svg>
            Calculators
          </div>
          <div className="px-3 py-2 rounded-md text-xs text-zinc-500 flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
            State guides
          </div>
        </div>
      </div>

      {/* Main panel */}
      <div className="flex-1 flex flex-col bg-zinc-950/80">
        {/* Header */}
        <div className="h-12 border-b border-zinc-800/50 flex items-center px-5 justify-between bg-zinc-900/20">
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-semibold text-zinc-200">Incident Reporting</span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-[9px] text-emerald-400 border border-emerald-500/25 font-medium">IR</span>
          </div>
          <div className="flex items-center gap-1.5">
            {['List', 'New report', 'AI insights'].map((t, i) => (
              <span key={t} className={`px-2 py-0.5 rounded text-[9px] font-medium transition-colors ${
                (step <= 1 && i === 0) || (step === 2 && i === 1) || (step >= 3 && i === 2)
                  ? 'bg-zinc-800 text-zinc-200 border border-zinc-600'
                  : 'text-zinc-600'
              }`}>{t}</span>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-5 overflow-hidden">
          <AnimatePresence mode="wait">

            {/* Step 1: Incidents list */}
            {step >= 1 && step < 2 && (
              <motion.div key="list" {...fade} className="space-y-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">14 open · 6 in review · 89 closed YTD</span>
                  <span className="text-[9px] text-emerald-500">Live across 4 locations</span>
                </div>
                {INCIDENTS.map((inc, i) => (
                  <motion.div
                    key={inc.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.12 }}
                    className="flex items-center gap-3 p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/30 hover:border-zinc-700 transition-colors"
                  >
                    <div className={`w-2 h-2 rounded-full shrink-0 ${
                      inc.sev === 'High' ? 'bg-red-400' : inc.sev === 'Med' ? 'bg-amber-400' : 'bg-zinc-500'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-zinc-500">{inc.id}</span>
                        <span className="text-xs font-medium text-zinc-200 truncate">{inc.loc}</span>
                      </div>
                      <div className="text-[10px] text-zinc-500 truncate">{inc.type} · {inc.when}</div>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[9px] font-medium ${
                      inc.status === 'open' ? 'bg-red-500/15 text-red-400 border border-red-500/25'
                      : inc.status === 'review' ? 'bg-amber-500/15 text-amber-400 border border-amber-500/25'
                      : 'bg-zinc-800 text-zinc-500 border border-zinc-700'
                    }`}>{inc.status}</span>
                  </motion.div>
                ))}
              </motion.div>
            )}

            {/* Step 2: New report w/ AI summary */}
            {step >= 2 && step < 3 && (
              <motion.div key="report" {...fade} className="space-y-3">
                <div className="p-4 rounded-lg border border-zinc-700/50 bg-zinc-900/50">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-zinc-100">New incident — Atlanta · Store 7</h3>
                    <span className="px-2 py-0.5 rounded bg-red-500/15 text-[9px] text-red-400 border border-red-500/25">High severity</span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-[11px] mb-3">
                    <div><span className="text-zinc-500">Reporter</span><div className="text-zinc-300 mt-0.5">Floor manager</div></div>
                    <div><span className="text-zinc-500">Witnesses</span><div className="text-zinc-300 mt-0.5">2 attached</div></div>
                    <div><span className="text-zinc-500">Photos</span><div className="text-zinc-300 mt-0.5">3 uploaded</div></div>
                  </div>
                  <div className="text-[11px] text-zinc-400 italic leading-relaxed border-l-2 border-zinc-700 pl-3">
                    "Customer escalated at register, raised voice. Crew member stayed calm, called manager. No physical contact."
                  </div>
                </div>
                <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                    <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">AI summary + flags</span>
                  </div>
                  <div className="text-[11px] text-zinc-300 leading-relaxed">
                    De-escalation handled correctly. <span className="text-amber-400">Flag:</span> 3rd customer escalation at this location in 14 days — recommend trend review.
                  </div>
                </div>
              </motion.div>
            )}

            {/* Step 3: Trend / risk by location */}
            {step >= 3 && (
              <motion.div key="trends" {...fade} className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Risk score by location · last 30d</span>
                  <span className="text-[9px] text-emerald-500">Updated 12m ago</span>
                </div>
                {RISK_LOCATIONS.map((loc, i) => (
                  <motion.div
                    key={loc.name}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.1 }}
                    className="flex items-center gap-3 p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/30"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-zinc-200 truncate">{loc.name}</div>
                      <div className="mt-1.5 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${loc.score}%` }}
                          transition={{ delay: i * 0.1 + 0.2, duration: 0.6 }}
                          className={`h-full ${
                            loc.score >= 70 ? 'bg-red-400' : loc.score >= 40 ? 'bg-amber-400' : 'bg-emerald-500'
                          }`}
                        />
                      </div>
                    </div>
                    <div className="text-right shrink-0 w-20">
                      <div className={`text-sm font-mono ${
                        loc.score >= 70 ? 'text-red-400' : loc.score >= 40 ? 'text-amber-400' : 'text-emerald-400'
                      }`}>{loc.score}</div>
                      <div className="text-[9px] text-zinc-500">{loc.count} incidents</div>
                    </div>
                  </motion.div>
                ))}
                <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
                  <div className="text-[11px] text-zinc-300 leading-relaxed">
                    <span className="font-semibold text-emerald-400">AI theme:</span> Weekend evening shift escalations clustered at Atlanta · Store 7 — recommend additional manager coverage Fri/Sat 6–10pm.
                  </div>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
