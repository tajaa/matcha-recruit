import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'

// Compliance product mockups for the /compliance landing pillars.
//
// Jurisdictional Compliance — the compliance ENGINE — gets a bespoke fan-out
// AUDIT FLOW: a regulation banner → central audit node → fans out to its
// required components, each with a gap/ok badge, citation, check question,
// and a suggested-fix subcard. This visual is deliberately unique to the
// engine; it's the one pillar that actually resolves a regulation into parts.
//
// Handbook Audit / Policy Management / Credentialing stay as the standard
// MatchaLiteMockup-style app-window dashboard: header tabs, a workflow
// stepper, big colored stat numbers with underline bars, detail rows, and a
// green callout. Both styles share the same sidebar chrome.

const C = {
  bg: '#0d0d10',
  borderSoft: 'rgba(39,39,42,0.5)',
  borderHard: 'rgba(63,63,70,0.5)',
  heading: '#f4f4f5',
  text: '#e4e4e7',
  textDim: '#a1a1aa',
  label: '#52525b',
  faint: '#3f3f46',
  red: '#ce5a4f',
  amber: '#c98a3e',
  jade: '#2f9e74',
  jadeLite: '#6ee7b7',
} as const

const ACCENT = { bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.25)', text: C.jadeLite }

type Screen = 'jurisdiction' | 'handbook' | 'policy' | 'credential'
type Tone = 'red' | 'amber' | 'green' | 'ink'
const toneColor = (t: Tone) => (t === 'red' ? C.red : t === 'amber' ? C.amber : t === 'green' ? C.jade : C.text)

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

// ── sidebar nav (shared by both mockup styles) ──────────────────────────────
const NAV: { screen: Screen | null; label: string; icon: React.ReactNode }[] = [
  { screen: 'jurisdiction', label: 'Jurisdictions', icon: <><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></> },
  { screen: 'handbook', label: 'Handbook Audit', icon: <><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/><path d="m9 9 2 2 4-4"/></> },
  { screen: 'policy', label: 'Policies', icon: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="14" x2="15" y2="14"/><line x1="9" y1="18" x2="13" y2="18"/></> },
  { screen: 'credential', label: 'Credentials', icon: <><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></> },
  { screen: null, label: 'Calendar', icon: <><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></> },
]
const RESOURCE_NAV: { label: string; icon: React.ReactNode }[] = [
  { label: 'Templates', icon: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></> },
  { label: 'Calculators', icon: <><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="6" x2="15" y2="6"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="13" y2="14"/></> },
  { label: 'State guides', icon: <><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></> },
]

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

function Sidebar({ screen }: { screen: Screen }) {
  return (
    <div className="hidden md:flex flex-col w-56 shrink-0 px-3 py-4" style={{ borderRight: `1px solid ${C.borderSoft}` }}>
      <div className="flex items-center gap-2 mb-7 px-2">
        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: C.jade, boxShadow: `0 0 8px ${C.jade}` }} />
        <span className="text-[11px] font-bold tracking-widest uppercase" style={{ color: C.text }}>Matcha Compliance</span>
      </div>
      <Label className="!font-bold mb-2 px-2">Compliance</Label>
      <div className="flex flex-col gap-0.5">
        {NAV.map(n => <NavItem key={n.label} active={n.screen === screen} icon={n.icon} label={n.label} />)}
      </div>
      <Label className="!font-bold mt-6 mb-2 px-2">Resources</Label>
      <div className="flex flex-col gap-0.5">
        {RESOURCE_NAV.map(n => <NavItem key={n.label} active={false} icon={n.icon} label={n.label} />)}
      </div>
    </div>
  )
}

// =============================================================================
// Dashboard mockup — Handbook Audit / Policy Management / Credentialing
// =============================================================================

type Stat = { label: string; value: string; sub: string; tone: Tone; pct: number }
type DetailRow = { label: string; tag: string; tone: Tone }

type ScreenConfig = {
  title: string
  chip: string
  tabs: string[]
  activeTab: number
  flow: string[]
  flowActive: number
  caption: string
  captionRight: string
  statsHeading: string
  stats: Stat[]
  rows: DetailRow[]
  callout: { label: string; body: string }
}

const SCREENS: Record<'handbook' | 'policy' | 'credential', ScreenConfig> = {
  handbook: {
    title: 'Handbook Audit',
    chip: 'CALIFORNIA',
    tabs: ['Gaps', 'Sections', 'Report'],
    activeTab: 0,
    flow: ['Upload handbook', 'Extract sections', 'Grade vs law', 'Rank gaps', 'Export report'],
    flowActive: 3,
    caption: 'Sections graded · 24',
    captionRight: 'vs california law',
    statsHeading: 'Coverage against state requirements',
    stats: [
      { label: 'Critical gaps', value: '3', sub: 'must fix', tone: 'red', pct: 100 },
      { label: 'Important', value: '5', sub: 'should fix', tone: 'amber', pct: 62 },
      { label: 'Covered', value: '71%', sub: '16 of 24', tone: 'green', pct: 71 },
    ],
    rows: [
      { label: 'Meal & rest breaks', tag: 'Critical', tone: 'red' },
      { label: 'Paid sick leave (HWHFA)', tag: 'Important', tone: 'amber' },
      { label: 'Overtime & classification', tag: 'Important', tone: 'amber' },
      { label: 'Anti-harassment policy', tag: 'Covered', tone: 'green' },
    ],
    callout: {
      label: 'Recommended:',
      body: 'add a compliant meal-and-rest-break section — Cal. Lab. Code §512.',
    },
  },
  policy: {
    title: 'Policy Library',
    chip: '23 TOTAL',
    tabs: ['All', 'Active', 'Suggested'],
    activeTab: 1,
    flow: ['Draft / upload', 'Jurisdiction check', 'Review', 'Publish', 'Review-date watch'],
    flowActive: 2,
    caption: 'Policies · 23',
    captionRight: 'updated 2d ago',
    statsHeading: 'Library by status',
    stats: [
      { label: 'Active', value: '18', sub: 'published', tone: 'green', pct: 78 },
      { label: 'In draft', value: '3', sub: 'in progress', tone: 'amber', pct: 32 },
      { label: 'Suggested', value: '2', sub: 'from patterns', tone: 'ink', pct: 18 },
    ],
    rows: [
      { label: 'Remote Work Policy', tag: 'Active', tone: 'green' },
      { label: 'Social Media Conduct', tag: 'Draft', tone: 'amber' },
      { label: 'Bereavement Leave', tag: 'Active', tone: 'green' },
      { label: 'Heat Illness Prevention', tag: 'Suggested', tone: 'amber' },
    ],
    callout: {
      label: 'Gap suggestion:',
      body: 'Heat Illness Prevention — surfaced from 3 incidents with no matching policy.',
    },
  },
  credential: {
    title: 'Credentials',
    chip: 'ICU · RN',
    tabs: ['Roster', 'Templates', 'Expiring'],
    activeTab: 2,
    flow: ['Define template', 'Auto-assign', 'Upload doc', 'OCR verify', 'Track expiry'],
    flowActive: 4,
    caption: 'Credentials tracked · 148',
    captionRight: '2 need attention',
    statsHeading: 'Expiration window',
    stats: [
      { label: 'Expired', value: '1', sub: 'action now', tone: 'red', pct: 100 },
      { label: '≤ 30 days', value: '1', sub: 'renew soon', tone: 'amber', pct: 40 },
      { label: 'Current', value: '146', sub: 'in good standing', tone: 'green', pct: 96 },
    ],
    rows: [
      { label: 'ACLS certification', tag: 'Expired', tone: 'red' },
      { label: 'BLS (CPR)', tag: '12 days', tone: 'amber' },
      { label: 'RN state license', tag: '142 days', tone: 'green' },
      { label: 'TB screening', tag: '88 days', tone: 'green' },
    ],
    callout: {
      label: 'Flagged:',
      body: 'ACLS expired 4 days ago — auto-assigned at hire, verified by OCR from the uploaded certificate.',
    },
  },
}

// Horizontal process-flow stepper — completed stages checked, active stage
// pulsing, connectors fill left-to-right on scroll-in.
function FlowStrip({ stages, active, inView }: { stages: string[]; active: number; inView: boolean }) {
  return (
    <div className="mb-4 pb-4" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
      <Label className="!font-bold block mb-3">Workflow</Label>
      <div className="flex items-start">
        {stages.map((s, i) => {
          const done = i < active
          const isActive = i === active
          const col = done || isActive ? C.jade : C.faint
          return (
            <div key={s} className="flex-1 min-w-0 flex flex-col items-center relative">
              {i > 0 && (
                <div className="absolute top-[8px] h-px" style={{ left: '-50%', right: '50%', backgroundColor: C.borderSoft }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={inView ? { width: i <= active ? '100%' : '0%' } : {}}
                    transition={{ delay: i * 0.15, duration: 0.4 }}
                    className="h-full"
                    style={{ backgroundColor: C.jade }}
                  />
                </div>
              )}
              <div
                className="relative z-10 w-[17px] h-[17px] rounded-full flex items-center justify-center"
                style={{ border: `1.5px solid ${col}`, backgroundColor: C.bg }}
              >
                {done ? (
                  <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                    <path d="M1 4l2 2 4-4" stroke={C.jade} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : isActive ? (
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: C.jade }}
                    animate={{ opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
                  />
                ) : (
                  <span className="w-1 h-1 rounded-full" style={{ backgroundColor: C.faint }} />
                )}
              </div>
              <span
                className="mt-2 text-[8px] font-mono uppercase tracking-wide text-center leading-tight px-0.5"
                style={{ color: isActive ? C.text : C.label }}
              >
                {s}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ComplianceDashboardMockup({ screen }: { screen: 'handbook' | 'policy' | 'credential' }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px', once: true })
  const cfg = SCREENS[screen]
  const wideStats = cfg.stats.length > 4

  return (
    <div
      ref={ref}
      className="relative w-full max-w-5xl mx-auto rounded-xl overflow-hidden shadow-2xl flex flex-col md:flex-row h-auto md:h-[520px] font-sans"
      style={{ backgroundColor: C.bg, border: `1px solid ${C.borderHard}` }}
    >
      <Sidebar screen={screen} />

      {/* Main panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center px-5 py-3.5 justify-between" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-bold" style={{ color: C.heading }}>{cfg.title}</span>
            <span className="px-1.5 py-0.5 rounded text-[8px] font-medium" style={{ backgroundColor: ACCENT.bg, color: ACCENT.text, border: `1px solid ${ACCENT.border}` }}>{cfg.chip}</span>
          </div>
          <div className="flex items-center gap-1.5">
            {cfg.tabs.map((t, i) => (
              <span key={t} className="px-2 py-1 rounded text-[8px] font-medium"
                style={cfg.activeTab === i
                  ? { backgroundColor: '#27272a', color: C.text, border: '1px solid #3f3f46' }
                  : { color: C.label, border: '1px solid transparent' }}>{t}</span>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 px-5 py-4 overflow-x-auto overflow-y-hidden">
          <FlowStrip stages={cfg.flow} active={cfg.flowActive} inView={inView} />

          <div className="flex items-center justify-between mb-2">
            <Label className="!font-bold flex items-center gap-2">
              <span className="font-mono normal-case tracking-normal" style={{ color: C.textDim }}>{cfg.caption}</span>
            </Label>
            <Micro color={C.jade} className="normal-case tracking-normal">{cfg.captionRight}</Micro>
          </div>

          {/* Stat row — big colored numbers + underline bars */}
          <Label className="!font-bold block pt-2 mb-2">{cfg.statsHeading}</Label>
          <div className="flex" style={{ borderTop: `1px solid ${C.borderSoft}` }}>
            {cfg.stats.map((s, i) => (
              <motion.div
                key={s.label}
                initial={{ opacity: 0, y: 8 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ delay: i * 0.08 }}
                className="flex-1 min-w-0 px-3 py-3 first:pl-0"
                style={{ borderLeft: i === 0 ? 'none' : `1px solid ${C.borderSoft}` }}
              >
                <Micro className="block truncate">{s.label}</Micro>
                <div className="font-bold tabular-nums leading-none mt-1.5" style={{ color: toneColor(s.tone), fontSize: wideStats ? '1.5rem' : '2rem', letterSpacing: '-0.02em' }}>{s.value}</div>
                <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(255,255,255,0.05)' }}>
                  <motion.div initial={{ width: 0 }} animate={inView ? { width: `${s.pct}%` } : {}} transition={{ delay: i * 0.08 + 0.2, duration: 0.6 }} className="h-full" style={{ backgroundColor: toneColor(s.tone) }} />
                </div>
                <Micro className="block mt-2">{s.sub}</Micro>
              </motion.div>
            ))}
          </div>

          {/* Detail rows */}
          <div className="mt-4">
            {cfg.rows.map((r, i) => (
              <motion.div
                key={r.label}
                initial={{ opacity: 0, x: -8 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ delay: 0.3 + i * 0.08 }}
                className="flex items-center gap-3 py-2.5"
                style={{ borderTop: `1px solid ${C.borderSoft}` }}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: toneColor(r.tone) }} />
                <span className="text-[13px] font-medium truncate flex-1" style={{ color: C.text }}>{r.label}</span>
                <Pill color={toneColor(r.tone)}>{r.tag}</Pill>
              </motion.div>
            ))}
          </div>

          {/* Callout */}
          <div className="pl-3 mt-4 text-[11px] leading-relaxed" style={{ borderLeft: `2px solid ${C.jade}`, color: C.textDim }}>
            <span className="font-semibold" style={{ color: C.jadeLite }}>{cfg.callout.label}</span> {cfg.callout.body}
          </div>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Fan-out audit-flow mockup — Jurisdictional Compliance (the engine) ONLY
// =============================================================================

type FlowTone = 'red' | 'amber' | 'green'
const FLOW_TC: Record<FlowTone, { c: string; lite: string }> = {
  red: { c: C.red, lite: '#e8a08f' },
  amber: { c: C.amber, lite: '#e3c07a' },
  green: { c: C.jade, lite: C.jadeLite },
}
// stacked-gradient card fill — mirrors the trend chart's 0.85→0.22 stops
const cardBg = (t: FlowTone) => `linear-gradient(180deg, ${FLOW_TC[t].c}2b 0%, ${FLOW_TC[t].c}0d 46%, ${FLOW_TC[t].c}00 100%)`

type Comp = { title: string; cite: string; tone: FlowTone; badge: string; question: string; fix: string }
type FlowConfig = {
  engine: string
  banner: { code: string; effective: string; summary: string; gapsLabel: string; gaps: string; exposure: string; exposureNote: string }
  central: string
  comps: Comp[]
  status: string
}

const JURISDICTION_FLOW: FlowConfig = {
  engine: 'Cal/OSHA',
  banner: {
    code: 'SB 553',
    effective: 'Effective Jul 1, 2024',
    summary: 'SF coffee chain · 8 locations · 87 employees · last audit: never',
    gapsLabel: 'Gaps',
    gaps: '5/5',
    exposure: '$200,000',
    exposureNote: 'Cal/OSHA serious violation × 8 locations',
  },
  central: 'SB 553 audit · 5 components',
  comps: [
    { title: 'Written WVP plan', cite: 'CA Lab §6401.9(c)', tone: 'red', badge: 'Gap', question: 'Plan exists, site-specific, employee-accessible?', fix: 'Draft plan · 8 sites × 4 risk types' },
    { title: 'Annual training', cite: 'CA Lab §6401.9(e)', tone: 'red', badge: 'Gap', question: 'All employees trained interactively < 12 months?', fix: '87 emp · interactive · bilingual' },
    { title: 'Violent incident log', cite: 'CA Lab §6401.9(f)', tone: 'red', badge: 'Gap', question: 'Log incidents + threats + near-misses, retain 5y?', fix: 'Deploy log · 5-year retention' },
    { title: 'Hazard assessment', cite: 'CA Lab §6401.9(c)(2)', tone: 'red', badge: 'Gap', question: 'Per-site assessment with workplace-specific hazards?', fix: '8 sites × 2hr walkthrough' },
    { title: 'Annual review', cite: 'CA Lab §6401.9(d)', tone: 'red', badge: 'Gap', question: 'Annual + post-incident review cadence in place?', fix: 'Schedule cadence + trigger rules' },
  ],
  status: 'Drafting remediation plan · sequencing dependencies…',
}

// fan-out connectors (central node → each component)
function FanLines({ n, inView }: { n: number; inView: boolean }) {
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-7 block" aria-hidden>
      <defs>
        <linearGradient id="fan-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={C.amber} stopOpacity={0.7} />
          <stop offset="100%" stopColor={C.jade} stopOpacity={0.35} />
        </linearGradient>
      </defs>
      {Array.from({ length: n }, (_, i) => {
        const x = ((i + 0.5) / n) * 100
        return (
          <motion.path
            key={i}
            d={`M50 2 C50 55, ${x} 45, ${x} 98`}
            fill="none"
            stroke="url(#fan-grad)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={inView ? { pathLength: 1, opacity: 1 } : {}}
            transition={{ delay: 0.2 + i * 0.1, duration: 0.5, ease: 'easeOut' }}
          />
        )
      })}
    </svg>
  )
}

function ComplianceFlowMockup() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px', once: true })
  const f = JURISDICTION_FLOW

  return (
    <div
      ref={ref}
      className="relative w-full rounded-xl overflow-hidden shadow-2xl flex flex-col md:flex-row h-auto font-sans"
      style={{ backgroundColor: C.bg, border: `1px solid ${C.borderHard}` }}
    >
      <Sidebar screen="jurisdiction" />

      {/* Main panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center px-5 py-3 justify-between" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
          <div className="flex items-center gap-2.5">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.textDim} strokeWidth="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M6 9v6"/><path d="M18 6a9 9 0 0 1-9 9"/><circle cx="18" cy="6" r="3"/></svg>
            <span className="text-sm font-semibold" style={{ color: C.heading }}>Compliance Analysis</span>
            <span className="px-1.5 py-0.5 rounded text-[8px] font-medium" style={{ backgroundColor: ACCENT.bg, color: ACCENT.text, border: `1px solid ${ACCENT.border}` }}>{f.banner.code.toUpperCase()} · LIVE</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.jade, boxShadow: `0 0 6px ${C.jade}` }} />
            <Micro color={C.textDim} className="normal-case tracking-normal">Live Engine · {f.engine}</Micro>
          </div>
        </div>

        {/* Flow content */}
        <div className="px-5 py-3.5">
          {/* Exposure banner */}
          <motion.div
            initial={{ opacity: 0, y: 8 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.4 }}
            className="rounded-lg px-3.5 py-2.5"
            style={{ background: `linear-gradient(180deg, ${C.red}24 0%, ${C.red}00 75%)`, border: `1px solid ${C.red}55` }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2 min-w-0">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.red} strokeWidth="2" className="mt-0.5 shrink-0"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-[12px] font-medium" style={{ color: FLOW_TC.red.lite }}>{f.banner.code}</span>
                    <Micro className="normal-case tracking-normal">{f.banner.effective}</Micro>
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: C.textDim }}>{f.banner.summary}</div>
                </div>
              </div>
              <div className="text-right shrink-0">
                <Micro className="block">{f.banner.gapsLabel}</Micro>
                <div className="font-bold tabular-nums leading-none mt-0.5" style={{ color: C.red, fontSize: '1.15rem' }}>{f.banner.gaps}</div>
              </div>
            </div>
            <div className="mt-1.5 pt-1.5 flex items-baseline gap-2 flex-wrap" style={{ borderTop: `1px solid ${C.red}2b` }}>
              <Micro className="normal-case tracking-normal">Exposure</Micro>
              <span className="text-[12px] font-medium" style={{ color: C.red }}>{f.banner.exposure}</span>
              <span className="text-[10px]" style={{ color: C.label }}>{f.banner.exposureNote}</span>
            </div>
          </motion.div>

          {/* Central node */}
          <div className="flex justify-center mt-2.5">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }} animate={inView ? { opacity: 1, scale: 1 } : {}} transition={{ delay: 0.15, duration: 0.35 }}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-lg"
              style={{ background: `linear-gradient(180deg, ${C.amber}24, ${C.jade}14)`, border: `1px solid ${C.amber}66`, boxShadow: `0 0 18px ${C.amber}22` }}
            >
              <motion.span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.amber }} animate={{ opacity: [1, 0.35, 1] }} transition={{ duration: 1.8, repeat: Infinity }} />
              <span className="text-[10px] font-medium tracking-wide" style={{ color: C.text }}>{f.central}</span>
            </motion.div>
          </div>

          {/* Fan-out connectors */}
          <FanLines n={f.comps.length} inView={inView} />

          {/* Component cards */}
          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${f.comps.length}, minmax(0,1fr))` }}>
            {f.comps.map((comp, i) => (
              <motion.div
                key={comp.title}
                initial={{ opacity: 0, y: 10 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.5 + i * 0.08, duration: 0.35 }}
                className="rounded-lg p-2 flex flex-col"
                style={{ background: cardBg(comp.tone), border: `1px solid ${FLOW_TC[comp.tone].c}55` }}
              >
                <div className="text-[9.5px] font-medium uppercase tracking-wide leading-tight" style={{ color: C.text }}>{comp.title}</div>
                <div className="text-[7.5px] font-mono mt-0.5" style={{ color: FLOW_TC[comp.tone].lite }}>{comp.cite}</div>
                <div className="mt-1.5">
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[7px] font-medium uppercase tracking-wider"
                    style={{ color: FLOW_TC[comp.tone].lite, backgroundColor: `${FLOW_TC[comp.tone].c}22`, border: `1px solid ${FLOW_TC[comp.tone].c}55` }}>
                    <span>{comp.tone === 'green' ? '✓' : '×'}</span>{comp.badge}
                  </span>
                </div>
                <div className="text-[9px] italic leading-snug mt-1.5 line-clamp-2" style={{ color: C.textDim }}>“{comp.question}”</div>
                <div className="mt-1.5">
                  <div className="rounded-md px-1.5 py-1" style={{ background: `linear-gradient(180deg, ${C.jade}1f 0%, ${C.jade}00 100%)`, border: `1px solid ${C.jade}44` }}>
                    <Micro color={C.jadeLite} className="block">Suggested fix</Micro>
                    <div className="text-[9px] leading-snug mt-0.5 line-clamp-2" style={{ color: C.text }}>{comp.fix}</div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Status bar */}
          <div className="flex items-center justify-between pt-2 mt-2.5" style={{ borderTop: `1px solid ${C.borderSoft}` }}>
            <div className="flex items-center gap-2 min-w-0">
              <Micro className="shrink-0">Status</Micro>
              <span className="text-[10px] truncate" style={{ color: C.amber, fontFamily: 'ui-monospace, monospace' }}>{f.status}</span>
            </div>
            <Micro className="normal-case tracking-normal shrink-0">Jurisdiction CA · {f.engine}</Micro>
          </div>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Public dispatcher
// =============================================================================

export function ComplianceMockup({ screen }: { screen: Screen }) {
  if (screen === 'jurisdiction') return <ComplianceFlowMockup />
  return <ComplianceDashboardMockup screen={screen} />
}
