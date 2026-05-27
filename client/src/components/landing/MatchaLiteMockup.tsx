import { useEffect, useRef, useState } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'

const INCIDENTS = [
  { id: 'INC-1042', loc: 'Atlanta — Store 7', type: 'Behavioral', sev: 'High', when: '2h ago', status: 'open' },
  { id: 'INC-1041', loc: 'Phoenix — Warehouse', type: 'Safety', sev: 'Med', when: '5h ago', status: 'review' },
  { id: 'INC-1040', loc: 'Denver — HQ', type: 'Property', sev: 'Low', when: '1d ago', status: 'closed' },
  { id: 'INC-1039', loc: 'Seattle — Store 12', type: 'Behavioral', sev: 'Med', when: '2d ago', status: 'closed' },
]

const RISK_LOCATIONS = [
  { name: 'Atlanta — Store 7', score: 78, count: 6 },
  { name: 'Phoenix — Warehouse', score: 54, count: 4 },
  { name: 'Denver — HQ', score: 22, count: 1 },
  { name: 'Seattle — Store 12', score: 41, count: 3 },
]

const OSHA_LOG = [
  { date: 'May 12', loc: 'Atlanta — Store 7', type: 'Strain/sprain', days: 3, recordable: true },
  { date: 'Apr 28', loc: 'Phoenix — Warehouse', type: 'Laceration', days: 1, recordable: true },
  { date: 'Mar 31', loc: 'Seattle — Store 12', type: 'Eye irritation', days: 2, recordable: true },
  { date: 'Mar 15', loc: 'Denver — HQ', type: 'Slip/fall', days: 0, recordable: false },
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
      setTimeout(() => setStep(2), 2600),
      setTimeout(() => setStep(3), 4800),
      setTimeout(() => setStep(4), 7000),
    ]
    return () => timers.forEach(clearTimeout)
  }, [inView])

  const isOsha = step === 3
  const activeTab = step <= 1 ? 0 : step === 2 ? 1 : step >= 4 ? 2 : -1

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
          <NavItem
            active={!isOsha && step > 0}
            icon={<><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></>}
            label="Incidents"
          />
          <NavItem
            active={false}
            icon={<><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></>}
            label="Trends"
          />
          <NavItem
            active={isOsha}
            icon={<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></>}
            label="OSHA 300"
          />
          <NavItem
            active={false}
            icon={<><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></>}
            label="Anonymous"
          />
          <NavItem
            active={false}
            icon={<><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>}
            label="Locations"
          />
        </div>

        <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mt-5 mb-2">Resources</div>
        <div className="flex flex-col gap-1">
          <NavItem active={false} icon={<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>} label="Templates" />
          <NavItem active={false} icon={<><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="6" x2="15" y2="6"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="13" y2="14"/></>} label="Calculators" />
          <NavItem active={false} icon={<><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></>} label="State guides" />
        </div>
      </div>

      {/* Main panel */}
      <div className="flex-1 flex flex-col bg-zinc-950/80">
        {/* Header */}
        <div className="h-12 border-b border-zinc-800/50 flex items-center px-5 justify-between bg-zinc-900/20">
          <div className="flex items-center gap-2.5">
            <AnimatePresence mode="wait">
              <motion.span
                key={isOsha ? 'osha' : 'ir'}
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="text-sm font-semibold text-zinc-200"
              >
                {isOsha ? 'OSHA 300 Log' : 'Incident Reporting'}
              </motion.span>
            </AnimatePresence>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-[9px] text-emerald-400 border border-emerald-500/25 font-medium">IR</span>
          </div>

          {isOsha ? (
            <button className="px-2.5 py-1 rounded bg-zinc-800 border border-zinc-600 text-[9px] text-zinc-300 font-medium">
              Export 300A
            </button>
          ) : (
            <div className="flex items-center gap-1.5">
              {(['List', 'New report', 'Risk insights'] as const).map((t, i) => (
                <span key={t} className={`px-2 py-0.5 rounded text-[9px] font-medium transition-colors ${
                  activeTab === i ? 'bg-zinc-800 text-zinc-200 border border-zinc-600' : 'text-zinc-600'
                }`}>{t}</span>
              ))}
            </div>
          )}
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
                    className="flex items-center gap-3 p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/30"
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

            {/* Step 2: New report + anonymous indicator + AI categorization */}
            {step >= 2 && step < 3 && (
              <motion.div key="report" {...fade} className="space-y-3">
                <div className="p-4 rounded-lg border border-zinc-700/50 bg-zinc-900/50">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-zinc-100">New incident — Atlanta · Store 7</h3>
                    <span className="px-2 py-0.5 rounded bg-red-500/15 text-[9px] text-red-400 border border-red-500/25">High severity</span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-[11px] mb-3">
                    <div>
                      <span className="text-zinc-500">Reporter</span>
                      <div className="text-zinc-300 mt-0.5">Floor manager</div>
                    </div>
                    <div>
                      <span className="text-zinc-500">Witnesses</span>
                      <div className="text-zinc-300 mt-0.5 flex items-center gap-1">
                        2 attached
                        <span className="text-[8px] text-zinc-500 bg-zinc-800 px-1 rounded">statements</span>
                      </div>
                    </div>
                    <div>
                      <span className="text-zinc-500">Photos</span>
                      <div className="text-zinc-300 mt-0.5 flex items-center gap-1">
                        3 uploaded
                        <span className="text-[8px] text-emerald-500 bg-emerald-500/10 px-1 rounded">✓</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-[11px] text-zinc-400 italic leading-relaxed border-l-2 border-zinc-700 pl-3">
                    "Customer escalated at register, raised voice. Crew member stayed calm, called manager. No physical contact."
                  </div>
                </div>

                <div className="p-2.5 rounded-lg border border-zinc-700/40 bg-zinc-900/30 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#71717a" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    <span className="text-[10px] text-zinc-400">Anonymous channel</span>
                  </div>
                  <span className="text-[9px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">1 new report</span>
                </div>

                <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                    <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">Suggested categorization + severity</span>
                  </div>
                  <div className="text-[11px] text-zinc-300 leading-relaxed">
                    Category: <span className="text-zinc-200 font-medium">Customer escalation / behavioral</span>. Severity: <span className="text-amber-400">Medium</span>. <span className="text-amber-400">Pattern:</span> 3rd escalation at this location in 14 days.
                  </div>
                </div>
              </motion.div>
            )}

            {/* Step 3: OSHA 300 log */}
            {step >= 3 && step < 4 && (
              <motion.div key="osha" {...fade} className="space-y-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Recordables YTD: 3 · Days away: 6 · Restricted: 0</span>
                  <span className="text-[9px] text-emerald-500">Auto-tallied</span>
                </div>
                <div className="rounded-lg border border-zinc-800/60 overflow-hidden">
                  <div className="grid gap-0 px-3 py-2 bg-zinc-800/40" style={{ gridTemplateColumns: '72px 1fr 100px 48px 72px' }}>
                    {['Date', 'Location', 'Injury type', 'Days', 'Recordable'].map(h => (
                      <span key={h} className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider">{h}</span>
                    ))}
                  </div>
                  {OSHA_LOG.map((row, i) => (
                    <motion.div
                      key={row.date + row.loc}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.1 }}
                      className="grid gap-0 px-3 py-2.5 border-t border-zinc-800/60 bg-zinc-900/20"
                      style={{ gridTemplateColumns: '72px 1fr 100px 48px 72px' }}
                    >
                      <span className="text-[10px] text-zinc-500">{row.date}</span>
                      <span className="text-[10px] text-zinc-300 truncate pr-2">{row.loc}</span>
                      <span className="text-[10px] text-zinc-400">{row.type}</span>
                      <span className="text-[10px] text-zinc-400">{row.days}d</span>
                      <span className={`text-[9px] font-medium ${row.recordable ? 'text-amber-400' : 'text-zinc-600'}`}>
                        {row.recordable ? '● Yes' : '○ No'}
                      </span>
                    </motion.div>
                  ))}
                </div>
                <div className="p-2.5 rounded-lg border border-zinc-700/40 bg-zinc-900/20 flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">300A summary ready for Feb 1 posting</span>
                  <span className="text-[9px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded cursor-pointer">Export PDF</span>
                </div>
              </motion.div>
            )}

            {/* Step 4: AI insights — risk score by location */}
            {step >= 4 && (
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
                    <span className="font-semibold text-emerald-400">Detected pattern:</span> Weekend evening escalations clustered at Atlanta · Store 7 — flagged for review, consider additional manager coverage Fri/Sat 6–10pm.
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

function NavItem({ active, icon, label }: { active: boolean; icon: React.ReactNode; label: string }) {
  return (
    <div className={`px-3 py-2 rounded-md text-xs flex items-center gap-2 transition-colors ${
      active ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-300' : 'text-zinc-500'
    }`}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        {icon}
      </svg>
      {label}
    </div>
  )
}
