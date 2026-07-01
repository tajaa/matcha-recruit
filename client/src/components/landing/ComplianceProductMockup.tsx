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
// Story-flow mockup — Jurisdictional Compliance (the engine) ONLY
//
// A plain full-width card, no sidebar — just the header + a 3-panel
// sequence (issue found → why it's required → resolved) connected by
// animated arrows, plus a stat strip. Literally readable left-to-right,
// no curve or axis to decode. Deliberately doesn't expose the actual
// citations/questions/fix-detail granularity — that's the audit mechanics,
// not the story this pillar needs to sell.
// =============================================================================

type StoryStage = { label: string; tone: Tone; heading: string; lines: string[] }

type StoryConfig = {
  code: string
  engine: string
  intro: { label: string; delta: string; note: string }
  stages: StoryStage[]
  stats: Stat[]
}

const JURISDICTION_STORY: StoryConfig = {
  code: 'SB 553',
  engine: 'Cal/OSHA',
  intro: { label: 'Gap exposure', delta: '$200,000', note: 'new location added' },
  stages: [
    { label: 'Issue', tone: 'red', heading: 'SB 553 · Written WVP plan', lines: ['8 locations flagged', 'no plan on file'] },
    { label: 'Reasoning', tone: 'amber', heading: 'Cal Lab §6401.9(c)', lines: ['requires a site-specific,', 'employee-accessible plan'] },
    { label: 'Resolved', tone: 'green', heading: 'Plan drafted', lines: ['assigned to 8 sites', 'tracked to done'] },
  ],
  stats: [
    { label: 'Gaps found', value: '5', sub: 'of 5 required', tone: 'red', pct: 100 },
    { label: 'Days to close', value: '12', sub: 'avg across gaps', tone: 'amber', pct: 40 },
    { label: 'Exposure eliminated', value: '−$200,000', sub: 'fully resolved', tone: 'green', pct: 100 },
    { label: 'Coverage', value: '100%', sub: 'all components', tone: 'green', pct: 100 },
  ],
}

function StoryPanel({ stage, delay, inView }: { stage: StoryStage; delay: number; inView: boolean }) {
  const color = toneColor(stage.tone)
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ delay, duration: 0.35 }}
      className="flex-1 min-w-0 rounded-lg p-3.5"
      style={{ background: `linear-gradient(180deg, ${color}1f 0%, ${color}00 70%)`, border: `1px solid ${color}55` }}
    >
      <Micro color={color} className="!font-bold block">{stage.label}</Micro>
      <div className="text-[13px] font-medium mt-1.5 leading-snug" style={{ color: C.text }}>{stage.heading}</div>
      <div className="mt-1.5 space-y-0.5">
        {stage.lines.map(line => (
          <div key={line} className="text-[11px] leading-snug" style={{ color: C.textDim }}>{line}</div>
        ))}
      </div>
    </motion.div>
  )
}

function StageConnector({ fromTone, toTone, delay, inView }: { fromTone: Tone; toTone: Tone; delay: number; inView: boolean }) {
  const fromColor = toneColor(fromTone)
  const toColor = toneColor(toTone)
  const gradId = `connector-${fromTone}-${toTone}`
  return (
    <div className="w-6 md:w-10 shrink-0 flex items-center justify-center">
      <svg width="100%" height="10" viewBox="0 0 40 10" preserveAspectRatio="none" aria-hidden>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={fromColor} />
            <stop offset="100%" stopColor={toColor} />
          </linearGradient>
        </defs>
        <motion.line
          x1={0} y1={5} x2={32} y2={5}
          stroke={`url(#${gradId})`}
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={inView ? { pathLength: 1, opacity: 1 } : {}}
          transition={{ delay, duration: 0.35, ease: 'easeOut' }}
        />
        <motion.path
          d="M30 1 L36 5 L30 9"
          fill="none"
          stroke={toColor}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ delay: delay + 0.3, duration: 0.2 }}
        />
      </svg>
    </div>
  )
}

function ComplianceFlowMockup() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px', once: true })
  const f = JURISDICTION_STORY

  return (
    <div
      ref={ref}
      className="relative w-full rounded-xl overflow-hidden shadow-2xl h-auto font-sans"
      style={{ backgroundColor: C.bg, border: `1px solid ${C.borderHard}` }}
    >
      {/* Header */}
      <div className="flex items-center px-5 py-3 justify-between" style={{ borderBottom: `1px solid ${C.borderSoft}` }}>
        <div className="flex items-center gap-2.5">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.textDim} strokeWidth="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M6 9v6"/><path d="M18 6a9 9 0 0 1-9 9"/><circle cx="18" cy="6" r="3"/></svg>
          <span className="text-sm font-semibold" style={{ color: C.heading }}>Compliance Analysis</span>
          <span className="px-1.5 py-0.5 rounded text-[8px] font-medium" style={{ backgroundColor: ACCENT.bg, color: ACCENT.text, border: `1px solid ${ACCENT.border}` }}>{f.code.toUpperCase()} · LIVE</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.jade, boxShadow: `0 0 6px ${C.jade}` }} />
          <Micro color={C.textDim} className="normal-case tracking-normal">Live Engine · {f.engine}</Micro>
        </div>
      </div>

      {/* Story content */}
      <div className="px-5 py-4">
        <div className="flex items-baseline gap-2 flex-wrap">
          <Micro className="normal-case tracking-normal">{f.intro.label}</Micro>
          <span className="text-[13px] font-medium" style={{ color: C.red }}>↗ {f.intro.delta}</span>
          <span className="text-[11px]" style={{ color: C.textDim }}>{f.intro.note}</span>
        </div>

        {/* 3-panel issue → reasoning → resolved flow */}
        <div className="mt-3 flex items-stretch">
          <StoryPanel stage={f.stages[0]} delay={0.1} inView={inView} />
          <StageConnector fromTone={f.stages[0].tone} toTone={f.stages[1].tone} delay={0.3} inView={inView} />
          <StoryPanel stage={f.stages[1]} delay={0.35} inView={inView} />
          <StageConnector fromTone={f.stages[1].tone} toTone={f.stages[2].tone} delay={0.55} inView={inView} />
          <StoryPanel stage={f.stages[2]} delay={0.6} inView={inView} />
        </div>

        {/* Stat strip — same big-number + underline-bar treatment as the other pillars */}
        <div className="flex mt-4" style={{ borderTop: `1px solid ${C.borderSoft}` }}>
          {f.stats.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 8 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.8 + i * 0.08 }}
              className="flex-1 min-w-0 px-3 py-3 first:pl-0"
              style={{ borderLeft: i === 0 ? 'none' : `1px solid ${C.borderSoft}` }}
            >
              <Micro className="block truncate">{s.label}</Micro>
              <div className="font-bold tabular-nums leading-none mt-1.5" style={{ color: toneColor(s.tone), fontSize: '1.5rem', letterSpacing: '-0.02em' }}>{s.value}</div>
              <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(255,255,255,0.05)' }}>
                <motion.div initial={{ width: 0 }} animate={inView ? { width: `${s.pct}%` } : {}} transition={{ delay: 0.8 + i * 0.08 + 0.2, duration: 0.6 }} className="h-full" style={{ backgroundColor: toneColor(s.tone) }} />
              </div>
              <Micro className="block mt-2">{s.sub}</Micro>
            </motion.div>
          ))}
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
