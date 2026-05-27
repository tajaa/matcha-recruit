import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'

// ───────────────────────────────────────────────────────────────────────────
// Neural-mesh take on the convergence story: EHS, GRC, and ER sit at the
// points of a triangle around a central DATA MODEL hub. Neon signal particles
// fire continuously between them — mostly routed through the hub, like a
// network passing context around. Canvas-rendered for additive neon glow +
// motion trails. Shares the dark card chrome of the other landing animations.
// ───────────────────────────────────────────────────────────────────────────

const EMERALD = '#34d399'
const AMBER = '#fbbf24'
const ROSE = '#fb7185'
const CYAN = '#7dd3fc'
const ZINC_LINE = 'rgba(255,255,255,0.08)'

type NodeId = 'hub' | 'ehs' | 'grc' | 'er'

interface NodeDef {
  id: NodeId
  tag: string
  sub: string
  color: string
  // position as fractions of the canvas (cssW, cssH)
  fx: number
  fy: number
}

const NODE_DEFS: NodeDef[] = [
  { id: 'hub', tag: 'DATA MODEL', sub: '', color: CYAN, fx: 0.5, fy: 0.54 },
  { id: 'ehs', tag: 'EHS', sub: 'Safety', color: EMERALD, fx: 0.5, fy: 0.17 },
  { id: 'grc', tag: 'GRC', sub: 'Compliance', color: AMBER, fx: 0.18, fy: 0.86 },
  { id: 'er', tag: 'ER', sub: 'Relations', color: ROSE, fx: 0.82, fy: 0.86 },
]

// Edges by node index into NODE_DEFS. Spokes first (routed through hub), then perimeter.
const SPOKES: [number, number][] = [[0, 1], [0, 2], [0, 3]]
const PERIMETER: [number, number][] = [[1, 2], [2, 3], [3, 1]]

const HUD_LINES = [
  'EHS → model · incident synced',
  'model → GRC · compliance gap flagged',
  'ER → model · behavioral pattern shared',
  'model → ER · case context pushed',
  'GRC → model · policy delta broadcast',
  'model → EHS · risk surfaced',
]

interface Particle {
  from: number
  to: number
  t: number
  speed: number
  color: string
}

export function NeuralConvergenceAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hud, setHud] = useState(HUD_LINES[0])

  // Cycle the footer ticker independently of the canvas loop.
  useEffect(() => {
    let i = 0
    const id = window.setInterval(() => {
      i = (i + 1) % HUD_LINES.length
      setHud(HUD_LINES[i])
    }, 2000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let cssW = 0
    let cssH = 0
    let dpr = window.devicePixelRatio || 1

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      cssW = rect.width
      cssH = rect.height
      dpr = window.devicePixelRatio || 1
      canvas.width = Math.round(cssW * dpr)
      canvas.height = Math.round(cssH * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    let visible = true
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting }, { rootMargin: '200px' })
    io.observe(container)

    const nodes = NODE_DEFS.map((d) => ({ ...d, x: 0, y: 0, r: 0, pulse: 0 }))
    const particles: Particle[] = []

    const pickEdge = (): [number, number] => {
      // 72% route through the hub (spokes), 28% perimeter.
      const pool = Math.random() < 0.72 ? SPOKES : PERIMETER
      const e = pool[(Math.random() * pool.length) | 0]
      return Math.random() < 0.5 ? e : [e[1], e[0]]
    }

    const spawn = (from?: number, to?: number) => {
      let f: number, t: number
      if (from !== undefined && to !== undefined) { f = from; t = to }
      else { const e = pickEdge(); f = e[0]; t = e[1] }
      const srcColor = nodes[f].id === 'hub' ? nodes[t].color : nodes[f].color
      particles.push({ from: f, to: t, t: 0, speed: 0.5 + Math.random() * 0.5, color: srcColor })
    }

    // seed a few
    for (let i = 0; i < 5; i++) spawn()

    let raf = 0
    let last = performance.now()
    let spawnAcc = 0

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw)
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      if (!visible || cssW === 0) return

      // Resolve node geometry
      const baseR = Math.max(16, Math.min(cssW, cssH) * 0.052)
      for (const n of nodes) {
        n.x = n.fx * cssW
        n.y = n.fy * cssH
        n.r = n.id === 'hub' ? baseR * 0.92 : baseR
        n.pulse *= 0.9
      }

      // Spawn cadence
      spawnAcc += dt
      while (spawnAcc > 0.13) {
        spawnAcc -= 0.13
        if (particles.length < 60) spawn()
      }

      // Trail fade (normal compositing)
      ctx.globalCompositeOperation = 'source-over'
      ctx.fillStyle = 'rgba(8,8,6,0.30)'
      ctx.fillRect(0, 0, cssW, cssH)

      // Edges — additive faint neon
      ctx.globalCompositeOperation = 'lighter'
      const allEdges = [...SPOKES, ...PERIMETER]
      for (const [a, b] of allEdges) {
        const na = nodes[a], nb = nodes[b]
        const grad = ctx.createLinearGradient(na.x, na.y, nb.x, nb.y)
        grad.addColorStop(0, hexA(na.color, 0.10))
        grad.addColorStop(1, hexA(nb.color, 0.10))
        ctx.strokeStyle = grad
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(na.x, na.y)
        ctx.lineTo(nb.x, nb.y)
        ctx.stroke()
      }

      // Particles
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i]
        p.t += p.speed * dt
        const a = nodes[p.from], b = nodes[p.to]
        const e = easeInOut(Math.min(1, p.t))
        const x = a.x + (b.x - a.x) * e
        const y = a.y + (b.y - a.y) * e

        ctx.shadowBlur = 14
        ctx.shadowColor = p.color
        ctx.fillStyle = p.color
        ctx.beginPath()
        ctx.arc(x, y, 2.6, 0, Math.PI * 2)
        ctx.fill()
        // bright core
        ctx.shadowBlur = 0
        ctx.fillStyle = 'rgba(255,255,255,0.85)'
        ctx.beginPath()
        ctx.arc(x, y, 1, 0, Math.PI * 2)
        ctx.fill()

        if (p.t >= 1) {
          nodes[p.to].pulse = 1
          // Chain through the hub: arriving at hub re-emits to another domain.
          if (nodes[p.to].id === 'hub' && Math.random() < 0.65) {
            const domains = [1, 2, 3].filter((d) => d !== p.from)
            spawn(p.to, domains[(Math.random() * domains.length) | 0])
          }
          particles.splice(i, 1)
        }
      }

      // Nodes — glow + ring (additive), then crisp labels (source-over)
      for (const n of nodes) {
        const glowR = n.r * (1.9 + n.pulse * 1.1)
        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, glowR)
        g.addColorStop(0, hexA(n.color, 0.30 + n.pulse * 0.4))
        g.addColorStop(1, hexA(n.color, 0))
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.arc(n.x, n.y, glowR, 0, Math.PI * 2)
        ctx.fill()

        ctx.shadowBlur = 12 + n.pulse * 18
        ctx.shadowColor = n.color
        ctx.strokeStyle = hexA(n.color, 0.65 + n.pulse * 0.35)
        ctx.lineWidth = n.id === 'hub' ? 2 : 1.6
        ctx.beginPath()
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx.stroke()

        if (n.id === 'hub') {
          // pulsing core dot
          ctx.fillStyle = hexA(CYAN, 0.5 + n.pulse * 0.5)
          ctx.beginPath()
          ctx.arc(n.x, n.y, n.r * 0.28, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      // Labels — crisp, no glow
      ctx.shadowBlur = 0
      ctx.globalCompositeOperation = 'source-over'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      for (const n of nodes) {
        if (n.id === 'hub') {
          ctx.fillStyle = CYAN
          ctx.font = '700 9px ui-monospace, SFMono-Regular, monospace'
          ctx.fillText('DATA', n.x, n.y - 4)
          ctx.fillText('MODEL', n.x, n.y + 5)
        } else {
          ctx.fillStyle = n.color
          ctx.font = '700 14px ui-monospace, SFMono-Regular, monospace'
          ctx.fillText(n.tag, n.x, n.y)
          ctx.fillStyle = 'rgba(154,138,112,0.95)'
          ctx.font = '8px ui-monospace, SFMono-Regular, monospace'
          ctx.fillText(n.sub.toUpperCase(), n.x, n.y + n.r + 11)
        }
      }
    }

    raf = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
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
      <div className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0" style={{ borderColor: ZINC_LINE }}>
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[10px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Live Mesh · EHS / GRC / ER
          </span>
          <span className="text-[7.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: CYAN, border: `1px solid ${CYAN}55` }}>
            routing
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[8.5px]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: CYAN }} />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ backgroundColor: CYAN }} />
          </span>
          <span style={{ color: '#9a8a70' }}>1 data model</span>
        </div>
      </div>

      {/* Canvas body */}
      <div className="relative" style={{ height: 430 }}>
        {/* Scan-line bg under the canvas */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.05]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" style={{ display: 'block' }} />
      </div>

      {/* Footer HUD */}
      <div
        className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[7.5px]"
        style={{ borderColor: ZINC_LINE, backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span style={{ color: '#6a737d' }}>Routing</span>
          <span className="truncate" style={{ color: CYAN }}>{hud}</span>
          <span style={{ color: CYAN, animation: 'neural-cursor 0.9s steps(1) infinite' }}>▎</span>
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

// Apply alpha to a #rrggbb hex.
function hexA(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

function easeInOut(p: number) {
  return p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
}
