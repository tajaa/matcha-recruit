import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Share2 } from 'lucide-react'

// ───────────────────────────────────────────────────────────────────────────
// Unified Risk Graph story: every safety / compliance / relations system used to
// live in its own silo — a logged incident here, a flagged gap there, a case
// opened somewhere else, none of them talking. Watch the scattered records get
// pulled into one connected graph: shared context, zero re-entry. A graph mesh,
// not a decision tree — deliberately distinct from AgentReasoningAnimation.
// ───────────────────────────────────────────────────────────────────────────

const EMERALD = '#34d399'
const AMBER = '#d7ba7d'
const CORAL = '#e0916b'
const ZINC_LINE = 'rgba(255,255,255,0.08)'

interface ElementNode {
  key: string
  label: string
  color: string
  // percentage coords within the body box
  scatter: { x: number; y: number }
  web: { x: number; y: number }
}

// Web coords = hexagonal ring around the center (50,50). Scatter coords = loose,
// flung toward the edges so the "before" reads as disconnected systems.
const ELEMENTS: ElementNode[] = [
  { key: 'logged', label: 'logged', color: EMERALD, scatter: { x: 14, y: 20 }, web: { x: 50, y: 16 } },
  { key: 'flagged', label: 'flagged', color: AMBER, scatter: { x: 84, y: 16 }, web: { x: 80, y: 34 } },
  { key: 'case', label: 'case opened', color: CORAL, scatter: { x: 90, y: 74 }, web: { x: 78, y: 70 } },
  { key: 'training', label: 'training due', color: AMBER, scatter: { x: 52, y: 88 }, web: { x: 50, y: 84 } },
  { key: 'gap', label: 'gap found', color: CORAL, scatter: { x: 10, y: 80 }, web: { x: 22, y: 70 } },
  { key: 'pattern', label: 'pattern matched', color: EMERALD, scatter: { x: 6, y: 48 }, web: { x: 20, y: 34 } },
]

// Mesh adjacency (indices into ELEMENTS): outer ring + two cross-links so it
// reads as a graph, not a polygon.
const EDGES: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0], // ring
  [0, 3], [1, 4], // cross-links through the middle
]

const CENTER = { x: 50, y: 50 }

const SYNTHESIS = {
  stats: [
    { label: 'Systems linked', value: '6' },
    { label: 'Manual re-entry', value: '0' },
    { label: 'Context shared', value: 'Full' },
    { label: 'Records', value: '1 graph' },
  ],
}

type Stage = 'idle' | 'scattered' | 'pulling' | 'linked' | 'synthesis' | 'reset'

export function ConvergenceAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [hud, setHud] = useState('Listening for new events…')

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

    async function loop() {
      while (!cancelled) {
        // RESET
        setStage('idle')
        setHud('Listening for new events…')
        await sleep(500)
        if (cancelled) return

        // SCATTERED — siloed systems, no links
        setStage('scattered')
        setHud('Siloed systems · no shared context')
        await sleep(1300)
        if (cancelled) return

        // PULLING — records drawn toward one graph
        setStage('pulling')
        setHud('Pulling records into one graph…')
        await sleep(1000)
        if (cancelled) return

        // LINKED — edges snap in
        setStage('linked')
        setHud('All records linked · one data model')
        await sleep(1600)
        if (cancelled) return

        // SYNTHESIS
        setStage('synthesis')
        setHud('Unified risk graph · full context shared')
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

  const synthesisVisible = stage === 'synthesis'
  const pulled = stage === 'pulling' || stage === 'linked' || stage === 'synthesis'
  const linked = stage === 'linked' || stage === 'synthesis'

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
            Unified Risk Graph
          </span>
          <span className="text-[7.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: AMBER, border: `1px solid ${AMBER}55` }}>
            one data model
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[8.5px]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: EMERALD }} />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ backgroundColor: EMERALD }} />
          </span>
          <span style={{ color: '#9a8a70' }}>Live · real-time graph</span>
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

        {/* GRAPH STAGE */}
        {!synthesisVisible && (
          <div className="relative w-full h-full">
            {/* before/after caption */}
            <div className="absolute top-3 left-0 right-0 flex justify-center pointer-events-none">
              <AnimatePresence mode="wait">
                <motion.span
                  key={pulled ? 'after' : 'before'}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  transition={{ duration: 0.35 }}
                  className="font-mono text-[8.5px] uppercase tracking-[0.2em]"
                  style={{ color: pulled ? EMERALD : '#6a737d' }}
                >
                  {pulled ? 'integrated · one connected graph' : 'siloed today · six systems, none talking'}
                </motion.span>
              </AnimatePresence>
            </div>

            <EdgeSvg linked={linked} />

            {/* Central anchor — the unified graph forms here */}
            <AnimatePresence>
              {linked && (
                <motion.div
                  key="anchor"
                  initial={{ opacity: 0, scale: 0.7 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.4, ease: 'easeOut' }}
                  className="absolute -translate-x-1/2 -translate-y-1/2 rounded-md px-2.5 py-1 flex items-center gap-1.5 z-10"
                  style={{
                    left: `${CENTER.x}%`,
                    top: `${CENTER.y}%`,
                    backgroundColor: 'rgba(20,20,16,0.95)',
                    border: `1px solid ${AMBER}66`,
                    boxShadow: `0 0 16px ${AMBER}33`,
                  }}
                >
                  <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: AMBER, boxShadow: `0 0 6px ${AMBER}` }} />
                  <span className="font-mono text-[9px] font-semibold tracking-wide uppercase" style={{ color: '#e4ded2' }}>1 risk graph</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Element nodes */}
            {ELEMENTS.map((node) => (
              <ElementChip key={node.key} node={node} pulled={pulled} linked={linked} />
            ))}
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

      {/* Footer HUD */}
      <div
        className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[7.5px]"
        style={{ borderColor: ZINC_LINE, backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span style={{ color: '#6a737d' }}>Status</span>
          <span className="truncate" style={{ color: synthesisVisible ? EMERALD : AMBER }}>{hud}</span>
          <span style={{ color: AMBER, animation: 'convergence-cursor 0.9s steps(1) infinite' }}>▎</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span style={{ color: '#6a737d' }}>Graph</span>
          <span style={{ color: '#9a8a70' }}>6 systems → 1 model</span>
        </div>
      </div>

      <style>{`
        @keyframes convergence-cursor {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ElementChip({ node, pulled, linked }: { node: ElementNode; pulled: boolean; linked: boolean }) {
  const pos = pulled ? node.web : node.scatter
  const c = node.color
  return (
    <motion.div
      className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full flex items-center gap-1.5 px-2.5 py-1 z-20"
      initial={false}
      animate={{
        left: `${pos.x}%`,
        top: `${pos.y}%`,
        opacity: pulled ? 1 : 0.4,
        scale: linked ? 1 : pulled ? 0.96 : 0.9,
      }}
      transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      style={{
        backgroundColor: 'rgba(20,20,16,0.9)',
        backdropFilter: 'blur(6px)',
        border: `1px solid ${pulled ? `${c}88` : 'rgba(255,255,255,0.1)'}`,
        boxShadow: pulled ? `0 0 14px ${c}44, inset 0 0 8px ${c}20` : 'none',
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: c, boxShadow: pulled ? `0 0 6px ${c}` : 'none' }} />
      <span className="font-mono text-[9px] tracking-wide whitespace-nowrap" style={{ color: pulled ? '#e4ded2' : '#6a737d' }}>
        {node.label}
      </span>
    </motion.div>
  )
}

function EdgeSvg({ linked }: { linked: boolean }) {
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none z-0" preserveAspectRatio="none">
      {EDGES.map(([a, b], i) => {
        const from = ELEMENTS[a].web
        const to = ELEMENTS[b].web
        const stroke = ELEMENTS[a].color
        return (
          <motion.line
            key={i}
            x1={`${from.x}%`}
            y1={`${from.y}%`}
            x2={`${to.x}%`}
            y2={`${to.y}%`}
            stroke={stroke}
            strokeWidth={1.1}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: linked ? 1 : 0, opacity: linked ? 0.7 : 0 }}
            transition={{ duration: 0.5, delay: linked ? i * 0.07 : 0 }}
            style={{ filter: linked ? `drop-shadow(0 0 4px ${stroke}aa)` : 'none' }}
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
          Scattered systems → one connected graph
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {SYNTHESIS.stats.map((s, i) => (
          <div key={s.label}>
            <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>{s.label}</div>
            <div
              className="font-mono font-semibold tabular-nums text-[16px]"
              style={{ color: i === 0 || i === 1 ? EMERALD : '#cbd5e1', marginTop: 2 }}
            >
              {s.value}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 pt-3 border-t flex items-center gap-3 font-mono text-[9px]" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span style={{ color: '#6a737d' }}>Siloed tools: <span style={{ color: '#cbd5e1' }}>separate entries across disconnected systems, context lost</span></span>
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
