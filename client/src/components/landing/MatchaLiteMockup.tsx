import { useEffect, useRef, useState } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'

// Matcha Lite product mockup for the landing hero. Styled to be a sibling of
// the RiskInsightsHero panel below it: deep #0d0d10 chrome, muted earthy
// palette (terracotta / ochre / jade), thin hairline dividers (no boxed
// cards), 7–8px mono uppercase labels, big colored stat numbers, and a
// stacked-gradient incident-trend area chart that mirrors the panel's curve.

const C = {
  bg: '#0d0d10',
  borderSoft: 'rgba(39,39,42,0.5)', // zinc-800/50
  borderHard: 'rgba(63,63,70,0.5)', // zinc-700/50
  heading: '#f4f4f5',
  text: '#e4e4e7',
  textDim: '#a1a1aa',
  label: '#52525b', // zinc-600
  faint: '#3f3f46', // zinc-700
  red: '#ce5a4f',
  redDeep: '#b54a3f',
  amber: '#c98a3e',
  jade: '#2f9e74',
  jadeLite: '#6ee7b7',
} as const

const ACCENT = { bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.25)', text: C.jadeLite }

const sevColor = (s: string) => (s === 'High' ? C.red : s === 'Med' ? C.amber : C.jade)

const INCIDENTS = [
  { id: 'INC-1042', loc: 'Atlanta — Store 7', type: 'Behavioral', sev: 'High', when: '2h ago', status: 'open' },
  { id: 'INC-1041', loc: 'Phoenix — Warehouse', type: 'Safety', sev: 'Med', when: '5h ago', status: 'review' },
  { id: 'INC-1040', loc: 'Dallas — Store 3', type: 'Safety', sev: 'Med', when: '9h ago', status: 'open' },
  { id: 'INC-1039', loc: 'Denver — HQ', type: 'Property', sev: 'Low', when: '1d ago', status: 'closed' },
  { id: 'INC-1038', loc: 'Seattle — Store 12', type: 'Behavioral', sev: 'Med', when: '2d ago', status: 'closed' },
  { id: 'INC-1037', loc: 'Chicago — Store 9', type: 'Behavioral', sev: 'Low', when: '4d ago', status: 'closed' },
]

const RISK_LOCATIONS = [
  { name: 'Atlanta', sub: 'Store 7', score: 78, count: 6 },
  { name: 'Dallas', sub: 'Store 3', score: 63, count: 5 },
  { name: 'Phoenix', sub: 'Warehouse', score: 54, count: 4 },
  { name: 'Miami', sub: 'Store 5', score: 48, count: 3 },
  { name: 'Seattle', sub: 'Store 12', score: 41, count: 3 },
  { name: 'Portland', sub: 'Warehouse', score: 31, count: 2 },
  { name: 'Denver', sub: 'HQ', score: 22, count: 1 },
  { name: 'Chicago', sub: 'Store 9', score: 12, count: 1 },
]

const OSHA_LOG = [
  { date: 'May 12', loc: 'Atlanta — Store 7', type: 'Strain/sprain', days: 3, recordable: true },
  { date: 'Apr 28', loc: 'Phoenix — Warehouse', type: 'Laceration', days: 1, recordable: true },
  { date: 'Apr 14', loc: 'Dallas — Store 3', type: 'Burn (minor)', days: 2, recordable: true },
  { date: 'Mar 31', loc: 'Seattle — Store 12', type: 'Eye irritation', days: 2, recordable: true },
  { date: 'Mar 15', loc: 'Denver — HQ', type: 'Slip/fall', days: 0, recordable: false },
]

const fade = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -4 } }

// ── trend chart (mirrors RiskInsightsHero's stacked gradient hump) ──────────
const TREND_LAYERS = [
  { key: 'critical', color: C.redDeep, amp: 6, spread: 4.6 },
  { key: 'elevated', color: C.amber, amp: 9, spread: 5.6 },
  { key: 'baseline', color: C.jade, amp: 7, spread: 7.2 },
] as const

const gaussian = (x: number, c: number, s: number) => Math.exp(-((x - c) ** 2) / (2 * s * s))

const TREND_DATA = Array.from({ length: 26 }, (_, x) => {
  const row: Record<string, number> = { x }
  for (const l of TREND_LAYERS) {
    const v = l.amp * gaussian(x, 19, l.spread) + l.amp * 0.5 * gaussian(x, 8, l.spread * 0.9) + l.amp * 0.22
    row[l.key] = Math.round(v * 10) / 10
  }
  return row
})

function TrendChart() {
  return (
    <div style={{ height: 132 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={TREND_DATA} margin={{ top: 6, right: 0, bottom: 0, left: -32 }}>
          <defs>
            {TREND_LAYERS.map(l => (
              <linearGradient key={l.key} id={`ml-${l.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={l.color} stopOpacity={0.85} />
                <stop offset="100%" stopColor={l.color} stopOpacity={0.22} />
              </linearGradient>
            ))}
          </defs>
          <XAxis dataKey="x" hide />
          <YAxis hide domain={[0, 32]} />
          {TREND_LAYERS.map(l => (
            <Area
              key={l.key}
              type="monotone"
              dataKey={l.key}
              stackId="1"
              stroke={l.color}
              strokeWidth={1.25}
              fill={`url(#ml-${l.key})`}
              animationDuration={900}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── tiny shared type helpers ────────────────────────────────────────────────
function Label({ children, color = C.label, className = '' }: { children: React.ReactNode; color?: string; className?: string }) {
  return <span className={`text-[8px] font-mono uppercase tracking-widest ${className}`} style={{ color }}>{children}</span>
}
function Micro({ children, color = C.label, className = '' }: { children: React.ReactNode; color?: string; className?: string }) {
  return <span className={`text-[7px] font-mono uppercase tracking-widest ${className}`} style={{ color }}>{children}</span>
}
function Pill({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-[7px] font-bold tracking-wider uppercase"
      style={{ color, backgroundColor: `${color}1f`, border: `1px solid ${color}40` }}>
      {children}
    </span>
  )
}

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
    <div
      ref={ref}
      className="relative w-full max-w-5xl mx-auto rounded-xl overflow-hidden shadow-2xl flex flex-col md:flex-row h-[520px] font-sans"
      style={{ backgroundColor: C.bg, border: `1px solid ${C.borderHard}` }}
    >
      {/* Sidebar */}
      <div className="hidden md:flex flex-col w-56 px-3 py-4" style={{ borderRight: `1px solid ${C.borderSoft}` }}>
        <div className="flex items-center gap-2 mb-7 px-2">
          <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: C.jade, boxShadow: `0 0 8px ${C.jade}` }} />
          <span className="text-[11px] font-bold tracking-widest uppercase" style={{ color: C.text }}>Matcha Daily</span>
        </div>

        <Label className="!font-bold mb-2 px-2">Risk + Safety</Label>
        <div className="flex flex-col gap-0.5">
          <NavItem active={!isOsha && step > 0} icon={<><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></>} label="Incidents" />
          <NavItem active={false} icon={<><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></>} label="Trends" />
          <NavItem active={isOsha} icon={<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></>} label="OSHA 300" />
          <NavItem active={false} icon={<><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></>} label="Anonymous" />
          <NavItem active={false} icon={<><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>} label="Locations" />
        </div>

        <Label className="!font-bold mt-6 mb-2 px-2">Resources</Label>
        <div className="flex flex-col gap-0.5">
          <NavItem active={false} icon={<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>} label="Templates" />
          <NavItem active={false} icon={<><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="6" x2="15" y2="6"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="13" y2="14"/></>} label="Calculators" />
          <NavItem active={false} icon={<><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></>} label="State guides" />
        </div>
      </div>

      {/* Main panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center px-5 py-3.5 justify-between" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
          <div className="flex items-center gap-2.5">
            <AnimatePresence mode="wait">
              <motion.span key={isOsha ? 'osha' : 'ir'} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
                className="text-sm font-bold" style={{ color: C.heading }}>
                {isOsha ? 'OSHA 300 Log' : 'Incident Reporting'}
              </motion.span>
            </AnimatePresence>
            <span className="px-1.5 py-0.5 rounded text-[8px] font-medium" style={{ backgroundColor: ACCENT.bg, color: ACCENT.text, border: `1px solid ${ACCENT.border}` }}>IR</span>
          </div>

          {isOsha ? (
            <span className="px-2 py-1 rounded text-[8px]" style={{ backgroundColor: '#18181b', border: `1px solid #27272a`, color: '#71717a' }}>Export 300A</span>
          ) : (
            <div className="flex items-center gap-1.5">
              {(['List', 'New report', 'Risk insights'] as const).map((t, i) => (
                <span key={t} className="px-2 py-1 rounded text-[8px] font-medium transition-colors"
                  style={activeTab === i
                    ? { backgroundColor: '#27272a', color: C.text, border: '1px solid #3f3f46' }
                    : { color: C.label, border: '1px solid transparent' }}>{t}</span>
              ))}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 px-5 py-4 overflow-x-auto overflow-y-hidden">
          <AnimatePresence mode="wait">

            {/* Step 1: Incidents list */}
            {step >= 1 && step < 2 && (
              <motion.div key="list" {...fade}>
                <div className="flex items-center justify-between pb-2.5 mb-1" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
                  <Label>14 open · 6 in review · 89 closed YTD</Label>
                  <Micro color={C.jade} className="normal-case tracking-normal">live · 8 locations</Micro>
                </div>
                {INCIDENTS.map((inc, i) => (
                  <motion.div key={inc.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.12 }}
                    className="flex items-center gap-3.5 py-3" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
                    <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: sevColor(inc.sev) }} />
                    <span className="text-[9px] font-mono shrink-0 w-16" style={{ color: C.faint }}>{inc.id}</span>
                    <span className="text-[13px] font-medium truncate flex-1" style={{ color: C.text }}>{inc.loc}</span>
                    <Micro className="hidden sm:block">{inc.type}</Micro>
                    <span className="text-[9px] font-mono shrink-0 w-12 text-right" style={{ color: C.faint }}>{inc.when}</span>
                    <Pill color={inc.status === 'open' ? C.red : inc.status === 'review' ? C.amber : '#71717a'}>{inc.status}</Pill>
                  </motion.div>
                ))}
              </motion.div>
            )}

            {/* Step 2: New report + anonymous + AI categorization */}
            {step >= 2 && step < 3 && (
              <motion.div key="report" {...fade} className="space-y-4">
                <div>
                  <div className="flex items-center justify-between pb-3 mb-3" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
                    <h3 className="text-sm font-bold" style={{ color: C.heading }}>New incident — Atlanta · Store 7</h3>
                    <Pill color={C.red}>High severity</Pill>
                  </div>
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div>
                      <Label className="block mb-1">Reporter</Label>
                      <span className="text-[12px]" style={{ color: C.textDim }}>Floor manager</span>
                    </div>
                    <div>
                      <Label className="block mb-1">Witnesses</Label>
                      <span className="text-[12px] flex items-center gap-1.5" style={{ color: C.textDim }}>2 attached <Micro>statements</Micro></span>
                    </div>
                    <div>
                      <Label className="block mb-1">Photos</Label>
                      <span className="text-[12px] flex items-center gap-1.5" style={{ color: C.textDim }}>3 uploaded <span style={{ color: C.jadeLite }}>✓</span></span>
                    </div>
                  </div>
                  <div className="text-[12px] italic leading-relaxed pl-3" style={{ color: C.textDim, borderLeft: `2px solid ${C.borderHard}` }}>
                    "Customer escalated at register, raised voice. Crew member stayed calm, called manager. No physical contact."
                  </div>
                </div>

                <div className="flex items-center justify-between py-2.5" style={{ borderTop: `1px solid ${C.borderSoft}`, borderBottom: `1px solid ${C.borderSoft}` }}>
                  <div className="flex items-center gap-2">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke={C.label} strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    <span className="text-[11px]" style={{ color: C.textDim }}>Anonymous channel</span>
                  </div>
                  <Pill color={C.amber}>1 new report</Pill>
                </div>

                <div className="pl-3" style={{ borderLeft: `2px solid ${C.jade}` }}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: C.jade }} />
                    <Label color={C.jadeLite} className="!font-bold">Suggested categorization + severity</Label>
                  </div>
                  <div className="text-[11px] leading-relaxed" style={{ color: C.textDim }}>
                    Category: <span className="font-medium" style={{ color: C.text }}>Customer escalation / behavioral</span>. Severity: <span style={{ color: C.amber }}>Medium</span>. <span style={{ color: C.amber }}>Pattern:</span> 3rd escalation at this location in 14 days.
                  </div>
                </div>
              </motion.div>
            )}

            {/* Step 3: OSHA 300 log */}
            {step >= 3 && step < 4 && (
              <motion.div key="osha" {...fade}>
                <div className="flex items-center justify-between pb-2.5 mb-2" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
                  <Label>Recordables YTD: 4 · Days away: 8 · Restricted: 0</Label>
                  <Micro color={C.jade} className="normal-case tracking-normal">auto-tallied</Micro>
                </div>
                <div className="grid gap-0 px-1 pb-2" style={{ gridTemplateColumns: '72px 1fr 110px 44px 64px' }}>
                  {['Date', 'Location', 'Injury type', 'Days', 'Recordable'].map(h => <Micro key={h} className="!font-bold">{h}</Micro>)}
                </div>
                {OSHA_LOG.map((row, i) => (
                  <motion.div key={row.date + row.loc} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.1 }}
                    className="grid gap-0 px-1 py-3" style={{ gridTemplateColumns: '72px 1fr 110px 44px 64px', borderTop: `1px solid ${C.borderSoft}` }}>
                    <span className="text-[11px] font-mono" style={{ color: C.label }}>{row.date}</span>
                    <span className="text-[12px] truncate pr-2" style={{ color: C.text }}>{row.loc}</span>
                    <span className="text-[11px]" style={{ color: C.textDim }}>{row.type}</span>
                    <span className="text-[11px] font-mono" style={{ color: C.textDim }}>{row.days}d</span>
                    <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: row.recordable ? C.amber : C.faint }}>{row.recordable ? '● Yes' : '○ No'}</span>
                  </motion.div>
                ))}
                <div className="flex items-center justify-between pt-3 mt-1" style={{ borderTop: `1px solid ${C.borderSoft}` }}>
                  <span className="text-[11px]" style={{ color: C.label }}>300A summary ready for Feb 1 posting</span>
                  <span className="px-2 py-0.5 rounded text-[8px]" style={{ color: C.jadeLite, backgroundColor: ACCENT.bg, border: `1px solid ${ACCENT.border}` }}>Export PDF</span>
                </div>
              </motion.div>
            )}

            {/* Step 4: Risk insights — trend chart + metric columns (mirrors panel below) */}
            {step >= 4 && (
              <motion.div key="trends" {...fade}>
                <div className="flex items-center justify-between mb-1">
                  <Label className="!font-bold flex items-center gap-2">
                    Incident Trend
                    <span className="font-mono normal-case tracking-normal" style={{ color: C.red }}>↗ +312% recent vs prior half</span>
                  </Label>
                  <Micro color={C.jade} className="normal-case tracking-normal">updated 12m ago</Micro>
                </div>
                <TrendChart />
                <div className="flex justify-between mt-1 mb-3" style={{ paddingLeft: 0 }}>
                  {['Mar 15', 'Apr 5', 'Apr 26', 'May 10', 'May 24'].map(d => <Micro key={d} color={C.faint} className="!tracking-normal normal-case">{d}</Micro>)}
                </div>

                <Label className="!font-bold block pt-3 mb-2" >Risk score by location · last 30d</Label>
                <div className="flex" style={{ borderTop: `1px solid ${C.borderSoft}` }}>
                  {RISK_LOCATIONS.map((loc, i) => {
                    const c = loc.score >= 70 ? C.red : loc.score >= 40 ? C.amber : C.jade
                    return (
                      <motion.div key={loc.name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
                        className="flex-1 min-w-0 px-3 py-3 first:pl-0" style={{ borderLeft: i === 0 ? 'none' : `1px solid ${C.borderSoft}` }}>
                        <Micro className="block truncate">{loc.name} · {loc.sub}</Micro>
                        <div className="font-bold tabular-nums leading-none mt-1.5" style={{ color: c, fontSize: '1.6rem', letterSpacing: '-0.02em' }}>{loc.score}</div>
                        <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(255,255,255,0.05)' }}>
                          <motion.div initial={{ width: 0 }} animate={{ width: `${loc.score}%` }} transition={{ delay: i * 0.08 + 0.2, duration: 0.6 }} className="h-full" style={{ backgroundColor: c }} />
                        </div>
                        <Micro className="block mt-2">{loc.count} incidents</Micro>
                      </motion.div>
                    )
                  })}
                </div>

                <div className="pl-3 mt-4 text-[11px] leading-relaxed" style={{ borderLeft: `2px solid ${C.jade}`, color: C.textDim }}>
                  <span className="font-semibold" style={{ color: C.jadeLite }}>Detected pattern:</span> Weekend evening escalations clustered at Atlanta · Store 7 — consider additional manager coverage Fri/Sat 6–10pm.
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
    <div className="px-3 py-2 rounded-md text-xs flex items-center gap-2.5 transition-colors relative"
      style={active ? { backgroundColor: 'rgba(255,255,255,0.045)', color: C.heading } : { color: C.label }}>
      {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full" style={{ backgroundColor: C.jade }} />}
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ opacity: active ? 1 : 0.7 }}>{icon}</svg>
      {label}
    </div>
  )
}
