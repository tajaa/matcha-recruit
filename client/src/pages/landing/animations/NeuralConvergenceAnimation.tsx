import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'

// ───────────────────────────────────────────────────────────────────────────
// Quiet mesh take on the convergence story: EHS, GRC, and ER sit at the points
// of a triangle around a central DATA MODEL hub. Signals drift between them —
// mostly routed through the hub — passing context around. Rendered as crisp SVG
// hairlines with a muted palette to match the other landing cards (no neon
// bloom, no trails). Calm and deliberate rather than arcade-y.
// ───────────────────────────────────────────────────────────────────────────

const EMERALD = '#86efac'
const AMBER = '#d7ba7d'
const CORAL = '#ce9178'
const IVORY = '#e4ded2'
const ZINC_LINE = 'rgba(255,255,255,0.08)'

const VB_W = 480
const VB_H = 300

type NodeId = 'hub' | 'ehs' | 'grc' | 'er'
interface NodeDef { id: NodeId; tag: string; sub: string; color: string; x: number; y: number; r: number }

const NODES: NodeDef[] = [
  { id: 'hub', tag: 'DATA MODEL', sub: '', color: IVORY, x: 240, y: 158, r: 22 },
  { id: 'ehs', tag: 'EHS', sub: 'Safety', color: EMERALD, x: 240, y: 56, r: 27 },
  { id: 'grc', tag: 'GRC', sub: 'Compliance', color: AMBER, x: 80, y: 248, r: 27 },
  { id: 'er', tag: 'ER', sub: 'Relations', color: CORAL, x: 400, y: 248, r: 27 },
]

// Edges by index into NODES. Spokes (through hub) first, then perimeter.
const SPOKES: [number, number][] = [[0, 1], [0, 2], [0, 3]]
const PERIMETER: [number, number][] = [[1, 2], [2, 3], [3, 1]]
const ALL_EDGES = [...SPOKES, ...PERIMETER]

const HUD_LINES = [
  'EHS → model · incident synced',
  'model → GRC · compliance gap flagged',
  'ER → model · behavioral pattern shared',
  'model → ER · case context pushed',
  'GRC → model · policy delta broadcast',
  'model → EHS · risk surfaced',
]

interface Particle { id: number; from: number; to: number; t: number; speed: number; color: string }
interface FrameState { particles: { x: number; y: number; color: string }[]; pulses: number[]; activeEdges: Set<string> }

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const easeInOut = (p: number) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2)
const edgeKey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`)

export function NeuralConvergenceAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hud, setHud] = useState(HUD_LINES[0])
  const [frame, setFrame] = useState<FrameState>({ particles: [], pulses: NODES.map(() => 0), activeEdges: new Set() })

  useEffect(() => {
    let i = 0
    const id = window.setInterval(() => {
      i = (i + 1) % HUD_LINES.length
      setHud(HUD_LINES[i])
    }, 2200)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    let visible = true
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting }, { rootMargin: '200px' })
    if (containerRef.current) io.observe(containerRef.current)

    const particles: Particle[] = []
    const pulses = NODES.map(() => 0)
    let nextId = 1
    let last = performance.now()
    let spawnAcc = 0

    const pickEdge = (): [number, number] => {
      const pool = Math.random() < 0.72 ? SPOKES : PERIMETER
      const e = pool[(Math.random() * pool.length) | 0]
      return Math.random() < 0.5 ? e : [e[1], e[0]]
    }
    const spawn = (from?: number, to?: number) => {
      let f: number, t: number
      if (from !== undefined && to !== undefined) { f = from; t = to }
      else { const e = pickEdge(); f = e[0]; t = e[1] }
      const color = NODES[f].id === 'hub' ? NODES[t].color : NODES[f].color
      particles.push({ id: nextId++, from: f, to: t, t: 0, speed: 0.34 + Math.random() * 0.16, color })
    }
    for (let k = 0; k < 3; k++) spawn()

    let raf = 0
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      if (!visible) return

      // spawn cadence — sparse and calm
      spawnAcc += dt
      while (spawnAcc > 0.55) {
        spawnAcc -= 0.55
        if (particles.length < 9) spawn()
      }

      for (let n = 0; n < pulses.length; n++) pulses[n] *= 0.94

      const active = new Set<string>()
      const rendered: { x: number; y: number; color: string }[] = []
      for (let p = particles.length - 1; p >= 0; p--) {
        const part = particles[p]
        part.t += part.speed * dt
        const a = NODES[part.from], b = NODES[part.to]
        const e = easeInOut(Math.min(1, part.t))
        rendered.push({ x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), color: part.color })
        active.add(edgeKey(part.from, part.to))
        if (part.t >= 1) {
          pulses[part.to] = 1
          if (NODES[part.to].id === 'hub' && Math.random() < 0.55) {
            const domains = [1, 2, 3].filter((d) => d !== part.from)
            spawn(part.to, domains[(Math.random() * domains.length) | 0])
          }
          particles.splice(p, 1)
        }
      }

      setFrame({ particles: rendered, pulses: [...pulses], activeEdges: active })
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); io.disconnect() }
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
          <Activity className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[10px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Live Mesh · EHS / GRC / ER
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
          <span style={{ color: '#9a8a70' }}>real-time routing</span>
        </div>
      </div>

      {/* Body */}
      <div className="relative" style={{ height: 430 }}>
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.05]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style={{ display: 'block' }}>
          {/* Edges — fine dotted hairlines; the carrying edge tints to its color */}
          {ALL_EDGES.map(([a, b], i) => {
            const na = NODES[a], nb = NODES[b]
            const isActive = frame.activeEdges.has(edgeKey(a, b))
            return (
              <line
                key={i}
                x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
                stroke={isActive ? nb.color : 'rgba(255,255,255,0.10)'}
                strokeOpacity={isActive ? 0.32 : 1}
                strokeWidth={isActive ? 1.1 : 0.8}
                strokeDasharray="1.5 5"
                style={{ transition: 'stroke 400ms, stroke-opacity 400ms' }}
              />
            )
          })}

          {/* Particles — small soft dots, no bloom */}
          {frame.particles.map((p, i) => (
            <g key={i}>
              <circle cx={p.x} cy={p.y} r={5} fill={p.color} opacity={0.12} />
              <circle cx={p.x} cy={p.y} r={2.2} fill={p.color} opacity={0.9} />
            </g>
          ))}

          {/* Nodes */}
          {NODES.map((n, idx) => {
            const pulse = frame.pulses[idx]
            return (
              <g key={n.id}>
                {/* gentle pulse ring on arrival */}
                {pulse > 0.02 && (
                  <circle cx={n.x} cy={n.y} r={n.r + pulse * 9} fill="none" stroke={n.color} strokeOpacity={pulse * 0.35} strokeWidth={0.75} />
                )}
                <circle
                  cx={n.x} cy={n.y} r={n.r}
                  fill={n.color} fillOpacity={0.04 + pulse * 0.06}
                  stroke={n.color} strokeOpacity={0.28 + pulse * 0.5} strokeWidth={1.3}
                />
                {n.id === 'hub' ? (
                  <>
                    <circle cx={n.x} cy={n.y} r={3.5} fill={IVORY} opacity={0.45 + pulse * 0.4} />
                    <text x={n.x} y={n.y + n.r + 13} textAnchor="middle" fontSize={7.5} fontFamily="ui-monospace, monospace" fill="#9a8a70" style={{ letterSpacing: '0.12em' }}>
                      DATA MODEL
                    </text>
                  </>
                ) : (
                  <>
                    <text x={n.x} y={n.y + 4} textAnchor="middle" fontSize={14} fontWeight={700} fontFamily="ui-monospace, monospace" fill={n.color}>
                      {n.tag}
                    </text>
                    <text x={n.x} y={n.y + n.r + 13} textAnchor="middle" fontSize={7.5} fontFamily="ui-monospace, monospace" fill="#6a737d" style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                      {n.sub}
                    </text>
                  </>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      {/* Footer HUD */}
      <div
        className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[7.5px]"
        style={{ borderColor: ZINC_LINE, backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span style={{ color: '#6a737d' }}>Routing</span>
          <span className="truncate" style={{ color: AMBER }}>{hud}</span>
          <span style={{ color: AMBER, animation: 'neural-cursor 0.9s steps(1) infinite' }}>▎</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span style={{ color: '#6a737d' }}>Mesh</span>
          <span style={{ color: '#9a8a70' }}>real-time</span>
        </div>
      </div>

      <style>{`
        @keyframes neural-cursor {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}
