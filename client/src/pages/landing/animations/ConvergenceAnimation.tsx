import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Share2, AlertTriangle } from 'lucide-react'

// ───────────────────────────────────────────────────────────────────────────
// Convergence story: one safety incident lands once, then fans out to all
// three usually-siloed domains — EHS logs it, GRC flags the compliance gap it
// exposes, ER opens a case off the behavioral pattern. One record, three
// synchronized workflows, zero manual re-entry. Mirrors the visual vocabulary
// of AgentReasoningAnimation (scenario → root → fan-out → columns → synthesis).
// ───────────────────────────────────────────────────────────────────────────

const EMERALD = '#34d399'
const AMBER = '#d7ba7d'
const CORAL = '#e0916b'
const ZINC_LINE = 'rgba(255,255,255,0.08)'

interface Domain {
  key: string
  tag: string
  sub: string
  color: string
  pill: string
  cite: string
  question: string
  action: string
  status: string
}

const DOMAINS: Domain[] = [
  {
    key: 'ehs',
    tag: 'EHS',
    sub: 'Safety',
    color: EMERALD,
    pill: 'LOGGED',
    cite: 'OSHA 300 · §1904',
    question: 'Recordable? Witnesses + photos attached?',
    action: 'Recordable entry · 5-yr retention',
    status: 'Routing → EHS · recordkeeping check',
  },
  {
    key: 'grc',
    tag: 'GRC',
    sub: 'Compliance',
    color: AMBER,
    pill: 'FLAGGED',
    cite: 'CA SB 553 · §6401.9(e)',
    question: 'WVP training current across all 8 sites?',
    action: 'Schedule training · 87 emp · bilingual',
    status: 'Routing → GRC · SB 553 cadence check',
  },
  {
    key: 'er',
    tag: 'ER',
    sub: 'Relations',
    color: CORAL,
    pill: 'CASE OPENED',
    cite: 'Case #C391',
    question: '3rd escalation at this location in 14 days?',
    action: 'Open ER case · assign investigator',
    status: 'Routing → ER · behavioral pattern match',
  },
]

const SCENARIO = {
  id: 'Incident #4827',
  when: 'Just now · Atlanta · Store 7',
  facts: 'Customer escalation · raised voice · crew de-escalated, no contact',
  severity: 'Medium',
}

const SYNTHESIS = {
  stats: [
    { label: 'Domains updated', value: '3' },
    { label: 'Manual re-entry', value: '0' },
    { label: 'Context shared', value: 'Full' },
    { label: 'Routed in', value: '1.4s' },
  ],
}

type Phase = 'pending' | 'routing' | 'done'

const INITIAL: Phase[] = DOMAINS.map(() => 'pending')

export function ConvergenceAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scenarioVisible, setScenarioVisible] = useState(false)
  const [rootVisible, setRootVisible] = useState(false)
  const [phases, setPhases] = useState<Phase[]>(INITIAL)
  const [synthesisVisible, setSynthesisVisible] = useState(false)
  const [stage, setStage] = useState<'idle' | 'routing' | 'synced' | 'reset'>('idle')
  const [hud, setHud] = useState('Listening for new events…')
  const [routedCount, setRoutedCount] = useState(0)

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

    const setPhase = (idx: number, p: Phase) =>
      setPhases((prev) => prev.map((x, i) => (i === idx ? p : x)))

    async function loop() {
      while (!cancelled) {
        // RESET
        setScenarioVisible(false)
        setRootVisible(false)
        setPhases(INITIAL)
        setSynthesisVisible(false)
        setRoutedCount(0)
        setStage('idle')
        setHud('Listening for new events…')
        await sleep(500)
        if (cancelled) return

        // INCIDENT LANDS
        setStage('routing')
        setHud('New incident captured · Atlanta · Store 7')
        setScenarioVisible(true)
        await sleep(1100)
        if (cancelled) return

        // ONE RECORD
        setHud('One record created · routing to 3 domains…')
        setRootVisible(true)
        await sleep(900)
        if (cancelled) return

        // FAN OUT TO EACH DOMAIN
        for (let i = 0; i < DOMAINS.length; i++) {
          if (cancelled) return
          setHud(DOMAINS[i].status)
          setPhase(i, 'routing')
          await sleep(620)
          setPhase(i, 'done')
          setRoutedCount((c) => c + 1)
          await sleep(420)
        }

        // SYNTHESIS
        if (cancelled) return
        setHud('All three workflows synchronized · full context shared')
        await sleep(600)
        setSynthesisVisible(true)
        setStage('synced')
        await sleep(6000)
        if (cancelled) return

        // FADE → loop
        setStage('reset')
        await sleep(1000)
      }
    }

    loop()
    return () => { cancelled = true; obs?.disconnect() }
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
      <div className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0" style={{ borderColor: ZINC_LINE }}>
        <div className="flex items-center gap-2">
          <Share2 className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[10px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Unified Risk Graph · EHS / GRC / ER
          </span>
          <span className="text-[7.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: AMBER, border: `1px solid ${AMBER}55` }}>
            1 data model
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[8.5px]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: EMERALD }} />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ backgroundColor: EMERALD }} />
          </span>
          <span style={{ color: '#9a8a70' }}>Live · real-time routing</span>
        </div>
      </div>

      {/* Body */}
      <div
        className="relative overflow-hidden"
        style={{ height: 430, transition: 'opacity 600ms ease', opacity: stage === 'reset' ? 0.15 : 1 }}
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
        <ParticleField />

        <div className="relative w-full h-full px-4 py-4 flex flex-col">
          {/* SCENARIO — the incoming incident */}
          <AnimatePresence>
            {scenarioVisible && !synthesisVisible && (
              <motion.div
                key="scenario"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.4 }}
                className="relative mx-auto"
                style={{ width: 500 }}
              >
                <div
                  className="rounded-lg px-4 py-2.5 flex items-start gap-3"
                  style={{
                    backgroundColor: 'rgba(224,145,107,0.06)',
                    border: `1px solid ${CORAL}55`,
                    boxShadow: `0 0 20px ${CORAL}22, inset 0 0 12px ${CORAL}10`,
                  }}
                >
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: CORAL }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-[12px] font-semibold" style={{ color: CORAL }}>{SCENARIO.id}</span>
                      <span className="font-mono text-[8.5px] uppercase tracking-wider" style={{ color: '#9a8a70' }}>{SCENARIO.when}</span>
                    </div>
                    <div className="font-mono text-[10px] mt-1" style={{ color: '#cbd5e1' }}>{SCENARIO.facts}</div>
                    <div className="font-mono text-[9px] mt-1.5 flex items-baseline gap-2">
                      <span style={{ color: '#6a737d' }}>Captured once</span>
                      <span style={{ color: '#3f3f46' }}>·</span>
                      <span style={{ color: '#9a8a70' }}>no duplicate entry</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>Severity</div>
                    <div className="font-mono text-[14px] font-bold mt-0.5" style={{ color: AMBER }}>{SCENARIO.severity}</div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ROOT + FAN-OUT TREE */}
          {!synthesisVisible && (
            <div className="relative flex-1 mt-4">
              <ConnectorSvg rootVisible={rootVisible} phases={phases} />

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
                    <RootNode routed={routedCount} />
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="absolute inset-x-0 grid grid-cols-3 gap-3 px-6" style={{ top: 76 }}>
                {DOMAINS.map((d, i) => (
                  <DomainColumn key={d.key} domain={d} phase={phases[i]} index={i} />
                ))}
              </div>
            </div>
          )}

          {/* SYNTHESIS */}
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
                  style={{ width: 640, maxWidth: '100%' }}
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
          <span className="truncate" style={{ color: stage === 'synced' ? EMERALD : AMBER }}>{hud}</span>
          <span style={{ color: AMBER, animation: 'convergence-cursor 0.9s steps(1) infinite' }}>▎</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span style={{ color: '#6a737d' }}>Domains</span>
          <span style={{ color: '#9a8a70' }}>EHS · GRC · ER</span>
        </div>
      </div>

      <style>{`
        @keyframes convergence-cursor {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
        @keyframes convergence-weigh {
          0%, 100% { opacity: 0.35; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function RootNode({ routed }: { routed: number }) {
  return (
    <div
      className="rounded-md px-3 py-1.5 flex items-center gap-2"
      style={{ backgroundColor: 'rgba(20,20,16,0.95)', border: `1px solid ${AMBER}66`, boxShadow: `0 0 16px ${AMBER}30` }}
    >
      <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: AMBER, boxShadow: `0 0 6px ${AMBER}` }} />
      <span className="font-mono text-[10px] font-semibold tracking-wide uppercase" style={{ color: '#e4ded2' }}>One record</span>
      <span className="font-mono text-[9px]" style={{ color: '#6a737d' }}>·</span>
      <span className="font-mono text-[9px]" style={{ color: '#9a8a70' }}>routed to {routed}/3</span>
    </div>
  )
}

function DomainColumn({ domain, phase, index }: { domain: Domain; phase: Phase; index: number }) {
  const isPending = phase === 'pending'
  const isRouting = phase === 'routing'
  const isDone = phase === 'done'
  const c = domain.color

  return (
    <div className="relative flex flex-col items-center gap-1.5">
      {/* Routing strip — the citation the domain matches against */}
      <div className="h-4 flex items-center justify-center w-full">
        <AnimatePresence>
          {isRouting && (
            <motion.div
              key="routing"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="font-mono text-[8px] tabular-nums"
              style={{ color: c, animation: 'convergence-weigh 0.6s ease-in-out infinite' }}
            >
              {domain.cite}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Domain node */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: isPending ? 0.3 : 1, y: 0, scale: isRouting ? 1.04 : 1 }}
        transition={{ duration: 0.35, delay: index * 0.05 }}
        className="rounded-md w-full px-2 py-1.5 text-center"
        style={{
          backgroundColor: 'rgba(20,20,16,0.85)',
          backdropFilter: 'blur(6px)',
          border: `1px solid ${isDone ? `${c}88` : isRouting ? `${c}88` : 'rgba(255,255,255,0.1)'}`,
          boxShadow: isRouting || isDone ? `0 0 14px ${c}44, inset 0 0 8px ${c}20` : 'none',
          transition: 'border-color 220ms, box-shadow 220ms',
        }}
      >
        <div className="font-mono text-[11px] font-bold tracking-wide" style={{ color: c }}>{domain.tag}</div>
        <div className="font-mono text-[8px] uppercase tracking-wider mt-0.5" style={{ color: '#9a8a70' }}>{domain.sub}</div>
      </motion.div>

      {/* Status pill */}
      <AnimatePresence>
        {isDone && (
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 22 }}
            className="rounded-full px-2 py-[2px] font-mono text-[8.5px] font-bold tracking-wider uppercase flex items-center gap-1"
            style={{ color: c, backgroundColor: `${c}15`, border: `1px solid ${c}55` }}
          >
            <span>✓</span>
            <span>{domain.pill}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Question / what it checked */}
      <AnimatePresence>
        {isDone && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            transition={{ duration: 0.3 }}
            className="font-mono text-[8px] italic text-center px-1"
            style={{ color: '#6a737d' }}
          >
            "{domain.question}"
          </motion.div>
        )}
      </AnimatePresence>

      {/* Action sprout */}
      <AnimatePresence>
        {isDone && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: 'easeOut' }}
            className="rounded-md w-full px-2 py-1.5 text-center mt-1"
            style={{ backgroundColor: `${c}0f`, border: `1px solid ${c}55`, boxShadow: `0 0 10px ${c}25` }}
          >
            <div className="font-mono text-[7.5px] uppercase tracking-wider mb-0.5" style={{ color: c }}>Action</div>
            <div className="font-mono text-[9px] leading-tight" style={{ color: '#cbd5e1' }}>{domain.action}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ConnectorSvg({ rootVisible, phases }: { rootVisible: boolean; phases: Phase[] }) {
  const cols = 3
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ top: 18, height: 72 }} preserveAspectRatio="none">
      {Array.from({ length: cols }).map((_, i) => {
        const xPct = ((i + 0.5) / cols) * 100
        const active = phases[i] !== 'pending'
        return (
          <motion.line
            key={i}
            x1="50%"
            y1="6"
            x2={`${xPct}%`}
            y2="62"
            stroke={active ? DOMAINS[i].color : 'rgba(255,255,255,0.12)'}
            strokeWidth={active ? 1.3 : 0.8}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: rootVisible ? 1 : 0, opacity: rootVisible ? 1 : 0 }}
            transition={{ duration: 0.5, delay: i * 0.08 }}
            style={{
              filter: active ? `drop-shadow(0 0 4px ${DOMAINS[i].color}aa)` : 'none',
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
        <span className="font-mono text-[11px] font-semibold uppercase tracking-wider" style={{ color: EMERALD }}>
          One incident → three synchronized workflows
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {SYNTHESIS.stats.map((s, i) => (
          <div key={s.label}>
            <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>{s.label}</div>
            <div
              className="font-mono font-semibold tabular-nums text-[16px]"
              style={{ color: i === 1 ? EMERALD : i === 0 ? EMERALD : '#cbd5e1', marginTop: 2 }}
            >
              {s.value}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 pt-3 border-t flex items-center gap-3 font-mono text-[9px]" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span style={{ color: '#6a737d' }}>Siloed tools: <span style={{ color: '#cbd5e1' }}>3 separate entries across 3 systems, context lost</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span>Matcha: <span style={{ color: EMERALD, fontWeight: 600 }}>1 record, shared everywhere</span></span>
      </div>
    </div>
  )
}

function ParticleField() {
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
          style={{ width: 2, height: 2, backgroundColor: EMERALD, opacity: 0.3, left: `${p.x}%`, top: `${p.y}%` }}
          animate={{ y: [0, -40, 0], opacity: [0, 0.5, 0], scale: [0.5, 1.2, 0.5] }}
          transition={{ duration: p.duration, repeat: Infinity, delay: p.delay, ease: 'easeInOut' }}
        />
      ))}
    </>
  )
}
