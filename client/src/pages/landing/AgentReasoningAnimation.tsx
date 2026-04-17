import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GitBranch, AlertTriangle } from 'lucide-react'

// ───────────────────────────────────────────────────────────────────────────
// Real CA scenario: SB 553 Workplace Violence Prevention.
// Effective Jul 2024 — every CA employer must have a written plan, training,
// log, hazard assessment, and annual review cadence. Most companies don't.
// Cal/OSHA penalties stack per-location — risk reads as catastrophic.
// The agent audits the gap, weighs which sub-rule each decision triggers,
// commits to a remediation path. The visible "weighing" of multiple §
// citations per decision is what makes this feel agentic rather than scripted.
// ───────────────────────────────────────────────────────────────────────────

interface Decision {
  id: string
  label: string
  weighing: string[]      // ≥2 candidate citations the agent considers
  question: string         // the question the agent ultimately commits to
  result: 'GAP' | 'OK'
  remediation: string      // what the company must do
  cite: string             // the chosen statute
  status: string           // HUD line for this decision
}

const DECISIONS: Decision[] = [
  {
    id: 'plan',
    label: 'Written WVP Plan',
    weighing: ['§6401.9(a)', '§6401.9(c)(1)', 'Cal/OSHA template'],
    question: 'Plan exists, site-specific, employee-accessible?',
    result: 'GAP',
    remediation: 'Draft plan · 8 sites × 4 risk types',
    cite: 'CA Lab §6401.9(c)',
    status: 'Wage agent → §6401.9 plan-component check',
  },
  {
    id: 'training',
    label: 'Annual Training',
    weighing: ['§6401.9(e)', '§6401.9(e)(1)', 'AB 2188 cross-ref'],
    question: 'All employees trained interactively < 12 months?',
    result: 'GAP',
    remediation: '87 emp · interactive · bilingual',
    cite: 'CA Lab §6401.9(e)',
    status: 'Training agent → §6401.9(e) effective Jul 2024',
  },
  {
    id: 'log',
    label: 'Violent Incident Log',
    weighing: ['§6401.9(f)', 'Cal/OSHA Form 300', 'GC §6770'],
    question: 'Log incidents + threats + near-misses, retain 5y?',
    result: 'GAP',
    remediation: 'Deploy log · 5-year retention',
    cite: 'CA Lab §6401.9(f)',
    status: 'Records agent → §6401.9(f) recordkeeping',
  },
  {
    id: 'hazard',
    label: 'Hazard Assessment',
    weighing: ['§6401.9(c)(2)', '§3203 IIPP', 'Type 1/2/3 risk'],
    question: 'Per-site assessment with workplace-specific hazards?',
    result: 'GAP',
    remediation: '8 sites × 2hr walkthrough',
    cite: 'CA Lab §6401.9(c)(2)',
    status: 'Risk agent → workplace-violence type 1/2/3 scan',
  },
  {
    id: 'review',
    label: 'Annual Review',
    weighing: ['§6401.9(d)', 'Post-incident trigger', 'Procedural'],
    question: 'Annual review + post-incident review cadence in place?',
    result: 'GAP',
    remediation: 'Schedule cadence + trigger rules',
    cite: 'CA Lab §6401.9(d)',
    status: 'Governance agent → §6401.9(d) review cadence',
  },
]

const SCENARIO = {
  bill: 'SB 553',
  effective: 'Effective Jul 1, 2024',
  facts: 'SF coffee chain · 8 locations · 87 employees · last audit: never',
  exposure: '$200,000',
  exposureSubtext: 'Cal/OSHA serious violation × 8 locations',
}

const SYNTHESIS = {
  laborHours: '~120 hours',
  timeline: '4 weeks',
  cost: '$8,400',
  exposureAvoided: '$200,000',
}

const EMERALD = '#34d399'
const RED = '#f87171'
const AMBER = '#d7ba7d'
const ZINC_LINE = 'rgba(255,255,255,0.08)'

// Phase ordering for the loop
type DecisionPhase = 'pending' | 'weighing' | 'committed' | 'remediated'

interface DecisionState {
  phase: DecisionPhase
  weighIdx: number   // which candidate is currently "in focus" during weighing
}

const INITIAL_STATES: DecisionState[] = DECISIONS.map(() => ({ phase: 'pending', weighIdx: 0 }))

export default function AgentReasoningAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scenarioVisible, setScenarioVisible] = useState(false)
  const [rootVisible, setRootVisible] = useState(false)
  const [states, setStates] = useState<DecisionState[]>(INITIAL_STATES)
  const [synthesisVisible, setSynthesisVisible] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'auditing' | 'synthesized' | 'reset'>('idle')
  const [hudStatus, setHudStatus] = useState('Initializing CA jurisdiction graph...')
  const [gapCount, setGapCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    const visible = { current: true }
    const el = containerRef.current
    let obs: IntersectionObserver | null = null
    if (el) {
      obs = new IntersectionObserver(([e]) => { visible.current = e.isIntersecting }, { rootMargin: '200px' })
      obs.observe(el)
    }

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        const start = performance.now()
        const tick = () => {
          if (cancelled) return resolve()
          if (!visible.current) { setTimeout(tick, 200); return }
          const elapsed = performance.now() - start
          const remaining = ms - elapsed
          if (remaining <= 0) resolve()
          else setTimeout(tick, Math.min(remaining, 200))
        }
        tick()
      })

    const updateState = (idx: number, patch: Partial<DecisionState>) => {
      setStates(prev => prev.map((s, i) => i === idx ? { ...s, ...patch } : s))
    }

    async function loop() {
      while (!cancelled) {
        // RESET
        setScenarioVisible(false)
        setRootVisible(false)
        setStates(INITIAL_STATES)
        setSynthesisVisible(false)
        setGapCount(0)
        setPhase('idle')
        setHudStatus('Initializing CA jurisdiction graph...')
        await sleep(400)
        if (cancelled) return

        // SCENARIO CARD
        setPhase('auditing')
        setHudStatus('Loading SB 553 statute · Lab Code §6401.9...')
        setScenarioVisible(true)
        await sleep(1100)
        if (cancelled) return

        // ROOT NODE
        setHudStatus('Decomposing audit into 5 component checks...')
        setRootVisible(true)
        await sleep(900)
        if (cancelled) return

        // PER-DECISION FAN
        for (let i = 0; i < DECISIONS.length; i++) {
          if (cancelled) return
          const d = DECISIONS[i]
          setHudStatus(d.status)

          // Stage 1: weighing — cycle through candidate § citations
          updateState(i, { phase: 'weighing', weighIdx: 0 })
          for (let w = 0; w < d.weighing.length; w++) {
            if (cancelled) return
            updateState(i, { weighIdx: w })
            await sleep(280)
          }

          // Stage 2: commit
          updateState(i, { phase: 'committed' })
          if (d.result === 'GAP') setGapCount((g) => g + 1)
          await sleep(420)
          if (cancelled) return

          // Stage 3: remediation sprout
          updateState(i, { phase: 'remediated' })
          await sleep(280)
        }

        // SYNTHESIS
        if (cancelled) return
        setHudStatus('Synthesizing remediation path · sequencing dependencies...')
        await sleep(700)
        setSynthesisVisible(true)
        setPhase('synthesized')
        setHudStatus('Audit complete · 5/5 gaps resolved · 4-week path published')
        await sleep(6000)
        if (cancelled) return

        // FADE → loop
        setPhase('reset')
        await sleep(1000)
      }
    }

    loop()
    return () => {
      cancelled = true
      obs?.disconnect()
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="relative w-full max-w-[900px] rounded-xl overflow-hidden mx-auto flex flex-col"
      style={{
        backgroundColor: '#0a0a08',
        color: '#d4d4d4',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 40px 80px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04) inset',
      }}
    >
      {/* Header */}
      <div
        className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: ZINC_LINE }}
      >
        <div className="flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[10px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Agent Reasoning · CA Compliance Audit
          </span>
          <span
            className="text-[7.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono"
            style={{ color: AMBER, border: `1px solid ${AMBER}55` }}
          >
            SB 553 · LIVE
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[8.5px]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: EMERALD }} />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ backgroundColor: EMERALD }} />
          </span>
          <span style={{ color: '#9a8a70' }}>Live Engine · Cal/OSHA</span>
        </div>
      </div>

      {/* Body */}
      <div
        className="relative overflow-hidden"
        style={{
          height: 440,
          transition: 'opacity 600ms ease',
          opacity: phase === 'reset' ? 0.15 : 1,
        }}
      >
        {/* Scan-line bg */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.06]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />

        {/* Floating particles for ambient feel */}
        <ParticleField />

        {/* Tree */}
        <div className="relative w-full h-full px-4 py-4 flex flex-col">
          {/* SCENARIO CARD */}
          <AnimatePresence>
            {scenarioVisible && !synthesisVisible && (
              <motion.div
                key="scenario"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.4 }}
                className="relative mx-auto"
                style={{ width: 460 }}
              >
                <div
                  className="rounded-lg px-4 py-2.5 flex items-start gap-3"
                  style={{
                    backgroundColor: 'rgba(248,113,113,0.06)',
                    border: `1px solid ${RED}55`,
                    boxShadow: `0 0 20px ${RED}22, inset 0 0 12px ${RED}10`,
                  }}
                >
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: RED }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-[12px] font-semibold" style={{ color: RED }}>
                        {SCENARIO.bill}
                      </span>
                      <span className="font-mono text-[8.5px] uppercase tracking-wider" style={{ color: '#9a8a70' }}>
                        {SCENARIO.effective}
                      </span>
                    </div>
                    <div className="font-mono text-[10px] mt-1" style={{ color: '#cbd5e1' }}>
                      {SCENARIO.facts}
                    </div>
                    <div className="font-mono text-[10px] mt-1.5 flex items-baseline gap-2">
                      <span style={{ color: '#6a737d' }}>Exposure</span>
                      <span className="font-semibold tabular-nums text-[13px]" style={{ color: RED }}>
                        {SCENARIO.exposure}
                      </span>
                      <span className="text-[8.5px]" style={{ color: '#6a737d' }}>
                        {SCENARIO.exposureSubtext}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>
                      Gaps
                    </div>
                    <div className="font-mono tabular-nums text-[20px] font-bold" style={{ color: gapCount > 0 ? RED : '#3f3f46' }}>
                      {gapCount}/5
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ROOT + TREE — only visible during audit phase */}
          {!synthesisVisible && (
            <div className="relative flex-1 mt-4">
              {/* SVG connector layer */}
              <ConnectorSvg rootVisible={rootVisible} states={states} />

              {/* Root node */}
              <AnimatePresence>
                {rootVisible && (
                  <motion.div
                    key="root"
                    initial={{ opacity: 0, scale: 0.92 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.35 }}
                    className="absolute"
                    style={{ top: 0, left: '50%', transform: 'translateX(-50%)' }}
                  >
                    <RootNode />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Decision columns */}
              <div
                className="absolute inset-x-0 grid grid-cols-5 gap-2 px-2"
                style={{ top: 64 }}
              >
                {DECISIONS.map((d, i) => (
                  <DecisionColumn key={d.id} decision={d} state={states[i]} index={i} />
                ))}
              </div>
            </div>
          )}

          {/* SYNTHESIS CARD — centered both axes when shown alone */}
          <div className="absolute inset-0 flex items-center justify-center px-4 pointer-events-none">
            <AnimatePresence>
              {synthesisVisible && (
                <motion.div
                  key="synthesis"
                  initial={{ opacity: 0, y: 30, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                  className="pointer-events-auto"
                  style={{ width: 720, maxWidth: '100%' }}
                >
                  <SynthesisCard />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* Footer HUD */}
      <div
        className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[7.5px]"
        style={{ borderColor: ZINC_LINE, backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span style={{ color: '#6a737d' }}>Status</span>
          <span
            className="truncate"
            style={{ color: phase === 'synthesized' ? EMERALD : AMBER }}
          >
            {hudStatus}
          </span>
          <span style={{ color: AMBER, animation: 'reasoning-cursor 0.9s steps(1) infinite' }}>▎</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span style={{ color: '#6a737d' }}>Jurisdiction</span>
          <span style={{ color: '#9a8a70' }}>CA</span>
          <span style={{ color: '#3f3f46' }}>·</span>
          <span style={{ color: '#9a8a70' }}>Cal/OSHA</span>
        </div>
      </div>

      <style>{`
        @keyframes reasoning-cursor {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
        @keyframes weigh-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function RootNode() {
  return (
    <div
      className="rounded-md px-3 py-1.5 flex items-center gap-2"
      style={{
        backgroundColor: 'rgba(20,20,16,0.95)',
        border: `1px solid ${AMBER}66`,
        boxShadow: `0 0 16px ${AMBER}30`,
      }}
    >
      <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: AMBER, boxShadow: `0 0 6px ${AMBER}` }} />
      <span className="font-mono text-[10px] font-semibold tracking-wide uppercase" style={{ color: '#e4ded2' }}>
        SB 553 audit
      </span>
      <span className="font-mono text-[9px]" style={{ color: '#6a737d' }}>·</span>
      <span className="font-mono text-[9px]" style={{ color: '#9a8a70' }}>5 components</span>
    </div>
  )
}

function DecisionColumn({ decision, state, index }: { decision: Decision; state: DecisionState; index: number }) {
  const isPending = state.phase === 'pending'
  const isWeighing = state.phase === 'weighing'
  const isCommitted = state.phase === 'committed' || state.phase === 'remediated'
  const showRemediation = state.phase === 'remediated'

  const accentColor = decision.result === 'GAP' ? RED : EMERALD

  return (
    <div className="relative flex flex-col items-center gap-1.5">
      {/* Weighing strip — candidate § citations cycling */}
      <div className="h-4 flex items-center justify-center w-full">
        <AnimatePresence>
          {isWeighing && (
            <motion.div
              key="weighing"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="font-mono text-[8px] tabular-nums"
              style={{ color: AMBER, animation: 'weigh-pulse 0.6s ease-in-out infinite' }}
            >
              {decision.weighing[state.weighIdx]}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Decision node */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{
          opacity: isPending ? 0.3 : 1,
          y: 0,
          scale: isWeighing ? 1.04 : 1,
        }}
        transition={{ duration: 0.35, delay: index * 0.06 }}
        className="rounded-md w-full px-2 py-1.5 text-center"
        style={{
          backgroundColor: 'rgba(20,20,16,0.85)',
          backdropFilter: 'blur(6px)',
          border: `1px solid ${
            isCommitted ? `${accentColor}88` : isWeighing ? `${AMBER}88` : 'rgba(255,255,255,0.1)'
          }`,
          boxShadow: isWeighing
            ? `0 0 14px ${AMBER}44, inset 0 0 8px ${AMBER}20`
            : isCommitted
              ? `0 0 14px ${accentColor}44, inset 0 0 8px ${accentColor}20`
              : 'none',
          transition: 'border-color 220ms, box-shadow 220ms',
        }}
      >
        <div className="font-mono text-[9px] uppercase tracking-wider" style={{ color: '#cbd5e1' }}>
          {decision.label}
        </div>
        {isCommitted && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className="font-mono text-[8.5px] mt-0.5"
            style={{ color: accentColor }}
          >
            {decision.cite}
          </motion.div>
        )}
      </motion.div>

      {/* Result badge */}
      <AnimatePresence>
        {isCommitted && (
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 22 }}
            className="rounded-full px-2 py-[2px] font-mono text-[9px] font-bold tracking-wider uppercase flex items-center gap-1"
            style={{
              color: accentColor,
              backgroundColor: `${accentColor}15`,
              border: `1px solid ${accentColor}55`,
            }}
          >
            <span>{decision.result === 'GAP' ? '✗' : '✓'}</span>
            <span>{decision.result}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Question (only shown briefly during commit) */}
      <AnimatePresence>
        {isCommitted && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            transition={{ duration: 0.3 }}
            className="font-mono text-[8px] italic text-center px-1"
            style={{ color: '#6a737d' }}
          >
            "{decision.question}"
          </motion.div>
        )}
      </AnimatePresence>

      {/* Remediation sprout */}
      <AnimatePresence>
        {showRemediation && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: 'easeOut' }}
            className="rounded-md w-full px-2 py-1.5 text-center mt-1"
            style={{
              backgroundColor: 'rgba(52,211,153,0.06)',
              border: `1px solid ${EMERALD}55`,
              boxShadow: `0 0 10px ${EMERALD}25`,
            }}
          >
            <div className="font-mono text-[7.5px] uppercase tracking-wider mb-0.5" style={{ color: EMERALD }}>
              Remediate
            </div>
            <div className="font-mono text-[9px] leading-tight" style={{ color: '#cbd5e1' }}>
              {decision.remediation}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ConnectorSvg({ rootVisible, states }: { rootVisible: boolean; states: DecisionState[] }) {
  // 5 columns, root above. SVG sits over the tree area.
  const cols = 5
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ top: 18, height: 60 }}
      preserveAspectRatio="none"
    >
      {Array.from({ length: cols }).map((_, i) => {
        const xPct = ((i + 0.5) / cols) * 100
        const isActive = states[i].phase !== 'pending'
        return (
          <motion.line
            key={i}
            x1="50%"
            y1="6"
            x2={`${xPct}%`}
            y2="50"
            stroke={isActive ? AMBER : 'rgba(255,255,255,0.12)'}
            strokeWidth={isActive ? 1.2 : 0.8}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: rootVisible ? 1 : 0, opacity: rootVisible ? 1 : 0 }}
            transition={{ duration: 0.5, delay: i * 0.08 }}
            style={{
              filter: isActive ? `drop-shadow(0 0 4px ${AMBER}88)` : 'none',
              transition: 'stroke 240ms, filter 240ms',
            }}
          />
        )
      })}
    </svg>
  )
}

function SynthesisCard() {
  return (
    <div
      className="rounded-lg px-5 py-4"
      style={{
        backgroundColor: 'rgba(20,30,22,0.92)',
        backdropFilter: 'blur(8px)',
        border: `1px solid ${EMERALD}66`,
        boxShadow: `0 0 36px ${EMERALD}33, inset 0 0 16px ${EMERALD}10`,
      }}
    >
      <div className="flex items-baseline gap-2 mb-3">
        <span
          className="font-mono text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: EMERALD }}
        >
          Remediation Path Synthesized
        </span>
        <span className="font-mono text-[8.5px]" style={{ color: '#6a737d' }}>
          5 dependencies sequenced · 0 unresolved
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <SynthesisStat label="Timeline" value={SYNTHESIS.timeline} accent={EMERALD} />
        <SynthesisStat label="Internal labor" value={SYNTHESIS.laborHours} accent="#cbd5e1" />
        <SynthesisStat label="Cost" value={SYNTHESIS.cost} accent="#cbd5e1" />
        <SynthesisStat label="Exposure avoided" value={SYNTHESIS.exposureAvoided} accent={EMERALD} large />
      </div>

      <div className="mt-3 pt-3 border-t flex items-center gap-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span className="font-mono text-[8.5px]" style={{ color: '#6a737d' }}>Sources</span>
        <span className="font-mono text-[9px]" style={{ color: '#9a8a70' }}>
          CA Lab §6401.9(a–f) · §3203 IIPP · Cal/OSHA enforcement guidance
        </span>
      </div>

      <div className="mt-2 flex items-center gap-3 font-mono text-[9px]" style={{ color: '#6a737d' }}>
        <span>Human paralegal: <span style={{ color: '#cbd5e1' }}>~4 hours, 6 statutes, 2 enforcement docs</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span>Matcha: <span style={{ color: EMERALD, fontWeight: 600 }}>2.1 seconds</span></span>
      </div>
    </div>
  )
}

function SynthesisStat({ label, value, accent, large = false }: { label: string; value: string; accent: string; large?: boolean }) {
  return (
    <div>
      <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>
        {label}
      </div>
      <div
        className={`font-mono font-semibold tabular-nums ${large ? 'text-[18px]' : 'text-[14px]'}`}
        style={{ color: accent, marginTop: 2 }}
      >
        {value}
      </div>
    </div>
  )
}

function ParticleField() {
  // 12 ambient emerald dots floating
  const particles = Array.from({ length: 12 }).map((_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    duration: 4 + Math.random() * 5,
    delay: Math.random() * 3,
  }))
  return (
    <>
      {particles.map((p) => (
        <motion.div
          key={p.id}
          className="absolute rounded-full"
          style={{
            width: 2,
            height: 2,
            backgroundColor: EMERALD,
            opacity: 0.3,
            left: `${p.x}%`,
            top: `${p.y}%`,
          }}
          animate={{
            y: [0, -40, 0],
            opacity: [0, 0.5, 0],
            scale: [0.5, 1.2, 0.5],
          }}
          transition={{
            duration: p.duration,
            repeat: Infinity,
            delay: p.delay,
            ease: 'easeInOut',
          }}
        />
      ))}
    </>
  )
}
