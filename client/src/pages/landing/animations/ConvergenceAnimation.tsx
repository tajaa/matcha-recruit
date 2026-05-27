import { useEffect, useState } from 'react'
import { Share2 } from 'lucide-react'

// Convergence graph — EHS, GRC, and ER orbit one shared data model.
// A signal routes domain -> hub -> domain, so every hop visibly passes
// through the central model: a safety incident raises a compliance flag,
// which opens an ER case, whose pattern feeds back to safety.

const VB_W = 480
const VB_H = 300

type Pt = { x: number; y: number }
const HUB: Pt = { x: 240, y: 170 }

type Domain = { key: 'ehs' | 'grc' | 'er'; tag: string; title: string; metric: string; color: string; at: Pt }
const DOMAINS: Domain[] = [
  { key: 'ehs', tag: 'EHS', title: 'Safety',     metric: '12 incidents', color: '#86efac', at: { x: 240, y: 58 } },
  { key: 'grc', tag: 'GRC', title: 'Compliance', metric: '3 gaps',       color: '#d7ba7d', at: { x: 80,  y: 250 } },
  { key: 'er',  tag: 'ER',  title: 'Relations',  metric: '5 cases',      color: '#ce9178', at: { x: 400, y: 250 } },
]
const BY_KEY: Record<string, Domain> = Object.fromEntries(DOMAINS.map((d) => [d.key, d]))

type NodeRef = 'hub' | Domain['key']
const ptOf = (n: NodeRef): Pt => (n === 'hub' ? HUB : BY_KEY[n].at)
const colorOf = (n: NodeRef): string => (n === 'hub' ? '#e4ded2' : BY_KEY[n].color)

// Ordered signal path. Every domain hop is mediated by the hub.
type Seg = { from: NodeRef; to: NodeRef; event: string }
const SEGS: Seg[] = [
  { from: 'ehs', to: 'hub', event: 'Safety incident logged · Atlanta · Store 7' },
  { from: 'hub', to: 'grc', event: 'Compliance gap flagged · SB 553' },
  { from: 'grc', to: 'hub', event: 'Routing through shared model…' },
  { from: 'hub', to: 'er',  event: 'ER case opened · #C391' },
  { from: 'er',  to: 'hub', event: 'Pattern matched across cases' },
  { from: 'hub', to: 'ehs', event: 'Risk surfaced back to safety' },
]

const TRAVEL_MS = 850
const HOLD_MS = 240
const SEG_MS = TRAVEL_MS + HOLD_MS
const RESET_MS = 1200
const CYCLE_MS = SEGS.length * SEG_MS + RESET_MS

// Precompute when the signal arrives at each segment's target.
const ARRIVALS = SEGS.map((s, i) => ({ node: s.to, t: i * SEG_MS + TRAVEL_MS }))

const easeInOut = (p: number) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2)
const lerp = (a: number, b: number, t: number) => a + (b - a) * t

export function ConvergenceAnimation() {
  const [clock, setClock] = useState(0)

  useEffect(() => {
    let raf = 0
    const start = performance.now()
    const tick = () => {
      setClock((performance.now() - start) % CYCLE_MS)
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [])

  // Active segment + pulse position.
  let activeSeg = -1
  let pulse: { x: number; y: number; color: string } | null = null
  for (let i = 0; i < SEGS.length; i++) {
    const segStart = i * SEG_MS
    if (clock >= segStart && clock < segStart + TRAVEL_MS) {
      activeSeg = i
      const p = easeInOut((clock - segStart) / TRAVEL_MS)
      const a = ptOf(SEGS[i].from)
      const b = ptOf(SEGS[i].to)
      pulse = { x: lerp(a.x, b.x, p), y: lerp(a.y, b.y, p), color: colorOf(SEGS[i].to) }
      break
    }
    if (clock >= segStart + TRAVEL_MS && clock < segStart + SEG_MS) { activeSeg = i; break }
  }

  // Node glow = exponential decay since its most recent arrival.
  const glowOf = (node: NodeRef): number => {
    let best = -1
    for (const a of ARRIVALS) if (a.node === node && a.t <= clock && a.t > best) best = a.t
    if (best < 0) return node === 'ehs' ? 0.5 : 0.28 // EHS is the resting origin
    const since = clock - best
    return 0.32 + 0.68 * Math.exp(-since / 650)
  }

  const currentEvent = activeSeg >= 0 ? SEGS[activeSeg].event : SEGS[SEGS.length - 1].event
  const hubGlow = glowOf('hub')

  return (
    <div className="w-full h-full flex flex-col relative" style={{ backgroundColor: '#0e0d0b', color: '#d4d4d4' }}>
      {/* Grid bg */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />

      {/* Header */}
      <div className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <div className="flex items-center gap-2">
          <Share2 className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Unified Risk Graph
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>3 domains</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#86efac' }}>real-time</span>
        </div>
      </div>

      {/* Graph — fills the card */}
      <div className="relative flex-1 min-h-0">
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style={{ display: 'block' }}>
          <defs>
            <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#e4ded2" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#e4ded2" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Spokes: hub <-> each domain */}
          {DOMAINS.map((d) => {
            const lit = activeSeg >= 0 && (
              (SEGS[activeSeg].from === 'hub' && SEGS[activeSeg].to === d.key) ||
              (SEGS[activeSeg].from === d.key && SEGS[activeSeg].to === 'hub')
            )
            return (
              <line
                key={`spoke-${d.key}`}
                x1={HUB.x} y1={HUB.y} x2={d.at.x} y2={d.at.y}
                stroke={lit ? d.color : 'rgba(255,255,255,0.10)'}
                strokeWidth={lit ? 1.8 : 1}
                strokeDasharray="4 4"
                style={{ transition: 'stroke 250ms, stroke-width 250ms' }}
              />
            )
          })}

          {/* Faint perimeter between domains — shows they're all connected */}
          {[['ehs', 'grc'], ['grc', 'er'], ['er', 'ehs']].map(([a, b]) => (
            <line
              key={`perim-${a}-${b}`}
              x1={BY_KEY[a].at.x} y1={BY_KEY[a].at.y} x2={BY_KEY[b].at.x} y2={BY_KEY[b].at.y}
              stroke="rgba(255,255,255,0.05)" strokeWidth={0.75} strokeDasharray="2 5"
            />
          ))}

          {/* Hub */}
          <circle cx={HUB.x} cy={HUB.y} r={46} fill="url(#hubGlow)" opacity={0.4 + hubGlow * 0.6} />
          <circle
            cx={HUB.x} cy={HUB.y} r={26}
            fill="#0e0d0b"
            stroke="#e4ded2" strokeOpacity={0.3 + hubGlow * 0.6} strokeWidth={1.4}
            style={{ filter: hubGlow > 0.7 ? 'drop-shadow(0 0 10px rgba(228,222,210,0.5))' : 'none', transition: 'all 200ms' }}
          />
          <text x={HUB.x} y={HUB.y + 2} textAnchor="middle" fontSize={8} fontFamily="ui-monospace, monospace" fill="#e4ded2" style={{ letterSpacing: '0.04em' }}>
            DATA
          </text>
          <text x={HUB.x} y={HUB.y + 11} textAnchor="middle" fontSize={8} fontFamily="ui-monospace, monospace" fill="#e4ded2" style={{ letterSpacing: '0.04em' }}>
            MODEL
          </text>

          {/* Traveling signal */}
          {pulse && (
            <>
              <circle cx={pulse.x} cy={pulse.y} r={9} fill={pulse.color} opacity={0.18} />
              <circle cx={pulse.x} cy={pulse.y} r={4.5} fill={pulse.color} style={{ filter: `drop-shadow(0 0 7px ${pulse.color})` }} />
            </>
          )}

          {/* Domain nodes */}
          {DOMAINS.map((d) => {
            const g = glowOf(d.key)
            return (
              <g key={d.key}>
                <circle
                  cx={d.at.x} cy={d.at.y} r={30}
                  fill={d.color} fillOpacity={0.05 + g * 0.10}
                  stroke={d.color} strokeOpacity={0.28 + g * 0.72} strokeWidth={1.6}
                  style={{ filter: g > 0.7 ? `drop-shadow(0 0 10px ${d.color}90)` : 'none', transition: 'all 200ms' }}
                />
                <text x={d.at.x} y={d.at.y + 4} textAnchor="middle" fontSize={15} fontWeight={700} fontFamily="ui-monospace, monospace" fill={d.color}>
                  {d.tag}
                </text>
                {/* Title + metric below the circle */}
                <text x={d.at.x} y={d.at.y + 47} textAnchor="middle" fontSize={9} fontFamily="ui-monospace, monospace" fill="#cfc7b8" style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {d.title}
                </text>
                <text x={d.at.x} y={d.at.y + 59} textAnchor="middle" fontSize={7.5} fontFamily="ui-monospace, monospace" fill="#6a737d">
                  {d.metric}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {/* Footer — live event ticker */}
      <div className="relative px-4 py-2 border-t flex items-center gap-2 shrink-0 font-mono text-[9px]" style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: '#86efac', boxShadow: '0 0 6px #86efac' }} />
        <span className="truncate" style={{ color: '#9a8a70' }}>{currentEvent}</span>
      </div>
    </div>
  )
}
