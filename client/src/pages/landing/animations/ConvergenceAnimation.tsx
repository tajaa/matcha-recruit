import { useEffect, useRef, useState } from 'react'
import { Share2 } from 'lucide-react'

// Convergence graph — EHS, GRC, and ER as three nodes on one data model.
// A signal pulses around the triangle: a safety incident raises a compliance
// flag, which opens an ER case, whose pattern feeds back to EHS.

type Node = { key: string; tag: string; title: string; color: string; x: number; y: number }

const NODES: Node[] = [
  { key: 'ehs', tag: 'EHS', title: 'Safety',     color: '#86efac', x: 160, y: 44  },
  { key: 'grc', tag: 'GRC', title: 'Compliance', color: '#d7ba7d', x: 64,  y: 150 },
  { key: 'er',  tag: 'ER',  title: 'Relations',  color: '#ce9178', x: 256, y: 150 },
]

// Ordered hops around the loop: EHS -> GRC -> ER -> EHS.
type Hop = { from: number; to: number; event: string }
const HOPS: Hop[] = [
  { from: 0, to: 1, event: 'Safety incident logged · Atlanta · Store 7' },
  { from: 1, to: 2, event: 'Compliance gap flagged · SB 553' },
  { from: 2, to: 0, event: 'ER case opened · pattern fed back' },
]

const SIZE_W = 320
const SIZE_H = 200

const HOP_MS = 1500       // travel time per hop
const HOLD_MS = 350       // pause once a node receives the signal
const RESET_PAUSE_MS = 1400
const CYCLE_MS = HOPS.length * (HOP_MS + HOLD_MS) + RESET_PAUSE_MS

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }

export function ConvergenceAnimation() {
  const [clock, setClock] = useState(0) // ms within the current cycle
  const startRef = useRef<number>(0)

  useEffect(() => {
    let raf = 0
    startRef.current = performance.now()
    const tick = () => {
      const elapsed = (performance.now() - startRef.current) % CYCLE_MS
      setClock(elapsed)
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [])

  // Determine which hop is active and the pulse progress along it.
  let activeHop = -1
  let progress = 0
  let arrivedNode = -1 // node currently lit from a just-completed hop
  let acc = 0
  for (let i = 0; i < HOPS.length; i++) {
    const travelEnd = acc + HOP_MS
    const holdEnd = travelEnd + HOLD_MS
    if (clock < travelEnd) { activeHop = i; progress = (clock - acc) / HOP_MS; break }
    if (clock < holdEnd) { activeHop = i; progress = 1; arrivedNode = HOPS[i].to; break }
    acc = holdEnd
  }

  // Per-node glow: source of active hop and any arrived node glow brightest.
  const glow = (idx: number): number => {
    if (idx === arrivedNode) return 1
    if (activeHop >= 0) {
      const hop = HOPS[activeHop]
      if (idx === hop.from && progress < 1) return 0.85
      if (idx === hop.to && progress >= 1) return 1
    }
    // EHS is the resting origin between cycles
    if (activeHop === -1 && idx === 0) return 0.7
    return 0.32
  }

  const pulse = (() => {
    if (activeHop < 0 || progress >= 1) return null
    const hop = HOPS[activeHop]
    const a = NODES[hop.from], b = NODES[hop.to]
    // ease-in-out for a nicer travel
    const e = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2
    return { x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), color: b.color }
  })()

  const currentEvent = activeHop >= 0 ? HOPS[activeHop].event : HOPS[HOPS.length - 1].event

  return (
    <div className="w-full h-full flex flex-col relative" style={{ backgroundColor: '#0e0d0b', color: '#d4d4d4' }}>
      {/* Grid bg */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
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
          <span style={{ color: '#6a737d' }}>1 data model</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#86efac' }}>real-time</span>
        </div>
      </div>

      {/* Graph */}
      <div className="relative flex-1 flex items-center justify-center min-h-0 overflow-hidden">
        <svg width={SIZE_W} height={SIZE_H} viewBox={`0 0 ${SIZE_W} ${SIZE_H}`} className="max-w-full max-h-full">
          {/* Edges */}
          {HOPS.map((hop, i) => {
            const a = NODES[hop.from], b = NODES[hop.to]
            const isActive = activeHop === i
            return (
              <line
                key={i}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={isActive ? b.color : 'rgba(255,255,255,0.12)'}
                strokeWidth={isActive ? 1.4 : 0.8}
                strokeDasharray="3 3"
                style={{ transition: 'stroke 300ms' }}
              />
            )
          })}

          {/* Center label */}
          <text x={160} y={120} textAnchor="middle" fontSize={7} fontFamily="ui-monospace, monospace" fill="#52525b" style={{ letterSpacing: '0.1em' }}>
            ONE DATA MODEL
          </text>

          {/* Traveling pulse */}
          {pulse && (
            <circle cx={pulse.x} cy={pulse.y} r={4} fill={pulse.color} style={{ filter: `drop-shadow(0 0 6px ${pulse.color})` }} />
          )}

          {/* Nodes */}
          {NODES.map((n, idx) => {
            const g = glow(idx)
            return (
              <g key={n.key} style={{ transition: 'opacity 300ms' }}>
                <circle
                  cx={n.x} cy={n.y} r={22}
                  fill={n.color} fillOpacity={0.06 + g * 0.12}
                  stroke={n.color} strokeOpacity={0.25 + g * 0.75} strokeWidth={1.4}
                  style={{ filter: g > 0.8 ? `drop-shadow(0 0 8px ${n.color}90)` : 'none', transition: 'all 300ms' }}
                />
                <text x={n.x} y={n.y - 2} textAnchor="middle" fontSize={10} fontWeight={700} fontFamily="ui-monospace, monospace" fill={n.color}>
                  {n.tag}
                </text>
                <text x={n.x} y={n.y + 9} textAnchor="middle" fontSize={6.5} fontFamily="ui-monospace, monospace" fill="#9a8a70" style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {n.title}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {/* Footer — live event ticker */}
      <div className="relative px-4 py-2 border-t flex items-center gap-2 shrink-0 font-mono text-[8.5px]" style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: '#86efac', boxShadow: '0 0 6px #86efac' }} />
        <span className="truncate" style={{ color: '#9a8a70' }}>{currentEvent}</span>
      </div>
    </div>
  )
}
