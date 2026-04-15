import { useEffect, useRef, useState } from 'react'
import { GitBranch } from 'lucide-react'
import * as THREE from 'three'

type NodeState = 'dim' | 'processing' | 'resolved'

interface NodeDef {
  level: 0 | 1 | 2
  pos: [number, number, number]
  parent?: number
  label: string
}

const NODES: NodeDef[] = [
  { level: 0, pos: [0, 1.4, 0], label: 'Compliance Agent' },
  { level: 1, pos: [-1.6, 0.2, 0.4], parent: 0, label: 'Jurisdiction' },
  { level: 1, pos: [0, 0.2, 0.6], parent: 0, label: 'Labor Law' },
  { level: 1, pos: [1.6, 0.2, 0.4], parent: 0, label: 'Risk' },
  { level: 2, pos: [-2.1, -1.1, 0.9], parent: 1, label: 'CA SB-553' },
  { level: 2, pos: [-1.1, -1.1, 0.9], parent: 1, label: 'NY WTPA' },
  { level: 2, pos: [-0.5, -1.1, 1.1], parent: 2, label: 'FLSA OT' },
  { level: 2, pos: [0.5, -1.1, 1.1], parent: 2, label: 'PTO Accrual' },
  { level: 2, pos: [1.1, -1.1, 0.9], parent: 3, label: 'OSHA 300' },
  { level: 2, pos: [2.1, -1.1, 0.9], parent: 3, label: 'BIPA' },
]

const RADII = [0.32, 0.22, 0.16]
const COLOR_DIM = new THREE.Color('#2a2620')
const COLOR_PROC = new THREE.Color('#d7ba7d')
const COLOR_RESOLVED = new THREE.Color('#86efac')
const COLOR_BRANCH_IDLE = new THREE.Color('#9a8a70')

interface Step {
  t: number
  fn: (api: TimelineApi) => void
}

interface TimelineApi {
  setNode: (i: number, s: NodeState) => void
  activateEdge: (childIdx: number) => void
  setScore: (n: number) => void
  setStatus: (s: string) => void
  reset: () => void
}

const STATUSES = [
  'Scanning compliance posture across jurisdictions...',
  'Dispatching sub-agents: jurisdiction, labor, risk...',
  'Cross-referencing CA SB-553, NY WTPA, FLSA, OSHA, BIPA...',
  'All requirements satisfied. 0 gaps.',
]

function makeLabelSprite(text: string) {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 96
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, 512, 96)
  ctx.font = '500 44px ui-monospace, "SF Mono", Menlo, monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#9a8a70'
  ctx.shadowColor = 'rgba(0,0,0,0.9)'
  ctx.shadowBlur = 8
  ctx.fillText(text.toUpperCase(), 256, 48)
  const tex = new THREE.CanvasTexture(canvas)
  tex.minFilter = THREE.LinearFilter
  tex.generateMipmaps = false
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.95 })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(1.2, 0.225, 1)
  return { sprite, mat, tex }
}

export default function AgentReasoningAnimation() {
  const containerRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef(0)
  const [score, setScore] = useState(42)
  const [status, setStatus] = useState(STATUSES[0])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.querySelector('canvas')?.remove()

    const w = el.clientWidth
    const h = el.clientHeight
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 100)
    camera.position.set(0, 0.8, 6)
    camera.lookAt(0, 0.2, 0)

    const root = new THREE.Group()
    scene.add(root)

    scene.add(new THREE.AmbientLight(0xffffff, 0.85))
    const pl = new THREE.PointLight(0xe4ded2, 1.2, 16)
    pl.position.set(2, 4, 5)
    scene.add(pl)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setSize(w, h)
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)

    const disposables: { dispose: () => void }[] = []

    // Nodes
    type N = {
      mesh: THREE.Mesh
      mat: THREE.MeshStandardMaterial
      wire: THREE.LineSegments
      wireMat: THREE.LineBasicMaterial
      ring: THREE.Mesh
      ringMat: THREE.MeshBasicMaterial
      state: NodeState
      pulsePhase: number
    }
    const nodes: N[] = NODES.map((def) => {
      const r = RADII[def.level]
      // Inner solid icosahedron
      const geo = new THREE.IcosahedronGeometry(r * 0.78, 0)
      const mat = new THREE.MeshStandardMaterial({
        color: COLOR_DIM,
        emissive: COLOR_DIM,
        emissiveIntensity: 0.0,
        roughness: 0.7,
        metalness: 0.1,
        flatShading: true,
      })
      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.set(...def.pos)
      root.add(mesh)
      disposables.push(geo, mat)

      // Wireframe shell
      const wireGeo = new THREE.IcosahedronGeometry(r, 1)
      const edgesGeo = new THREE.EdgesGeometry(wireGeo)
      const wireMat = new THREE.LineBasicMaterial({ color: 0x9a8a70, transparent: true, opacity: 0.35 })
      const wire = new THREE.LineSegments(edgesGeo, wireMat)
      wire.position.set(...def.pos)
      root.add(wire)
      disposables.push(wireGeo, edgesGeo, wireMat)

      // Outer ring (orbit)
      const ringGeo = new THREE.RingGeometry(r * 1.35, r * 1.42, 48)
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0xd7ba7d,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
      })
      const ring = new THREE.Mesh(ringGeo, ringMat)
      ring.position.set(...def.pos)
      ring.lookAt(camera.position)
      root.add(ring)
      disposables.push(ringGeo, ringMat)

      const lbl = makeLabelSprite(def.label)
      const yOff = def.level === 0 ? 0.55 : def.level === 1 ? 0.45 : -0.38
      lbl.sprite.position.set(def.pos[0], def.pos[1] + yOff, def.pos[2])
      const scale = def.level === 0 ? 2.2 : def.level === 1 ? 1.75 : 1.45
      lbl.sprite.scale.set(scale, scale * 0.1875, 1)
      root.add(lbl.sprite)
      disposables.push(lbl.mat, lbl.tex)

      return { mesh, mat, wire, wireMat, ring, ringMat, state: 'dim' as NodeState, pulsePhase: Math.random() * Math.PI * 2 }
    })

    // Edges (one per non-root node, indexed by child index)
    type E = { line: THREE.Line; mat: THREE.LineBasicMaterial; targetOpacity: number; from: THREE.Vector3; to: THREE.Vector3; particle?: THREE.Mesh; particleMat?: THREE.MeshBasicMaterial; particleT: number; active: boolean }
    const edges: (E | null)[] = NODES.map((def, i) => {
      if (def.parent === undefined) return null
      const from = new THREE.Vector3(...NODES[def.parent].pos)
      const to = new THREE.Vector3(...def.pos)
      const geo = new THREE.BufferGeometry().setFromPoints([from, to])
      const mat = new THREE.LineBasicMaterial({ color: 0x9a8a70, transparent: true, opacity: 0.08 })
      const line = new THREE.Line(geo, mat)
      root.add(line)
      disposables.push(geo, mat)
      void i
      return { line, mat, targetOpacity: 0.08, from, to, particleT: 0, active: false }
    })

    // Visibility
    const vis = { current: true }
    const obs = new IntersectionObserver(([e]) => { vis.current = e.isIntersecting }, { rootMargin: '200px' })
    obs.observe(el)

    // Timeline
    const steps: Step[] = [
      { t: 0, fn: (a) => { a.reset(); a.setNode(0, 'processing'); a.setStatus(STATUSES[0]) } },
      { t: 600, fn: (a) => { a.activateEdge(1); a.setNode(1, 'processing') } },
      { t: 1000, fn: (a) => { a.activateEdge(2); a.setNode(2, 'processing') } },
      { t: 1400, fn: (a) => { a.activateEdge(3); a.setNode(3, 'processing') } },
      { t: 1600, fn: (a) => { a.setStatus(STATUSES[1]) } },
      { t: 2000, fn: (a) => { a.activateEdge(4); a.setNode(4, 'processing'); a.setStatus(STATUSES[2]) } },
      { t: 2400, fn: (a) => { a.setNode(4, 'resolved'); a.setScore(51) } },
      { t: 2600, fn: (a) => { a.activateEdge(5); a.setNode(5, 'processing') } },
      { t: 3000, fn: (a) => { a.setNode(5, 'resolved'); a.setScore(60) } },
      { t: 3200, fn: (a) => { a.activateEdge(6); a.setNode(6, 'processing') } },
      { t: 3600, fn: (a) => { a.setNode(6, 'resolved'); a.setScore(69) } },
      { t: 3800, fn: (a) => { a.activateEdge(7); a.setNode(7, 'processing') } },
      { t: 4200, fn: (a) => { a.setNode(7, 'resolved'); a.setScore(78) } },
      { t: 4400, fn: (a) => { a.activateEdge(8); a.setNode(8, 'processing') } },
      { t: 4800, fn: (a) => { a.setNode(8, 'resolved'); a.setScore(87) } },
      { t: 5000, fn: (a) => { a.activateEdge(9); a.setNode(9, 'processing') } },
      { t: 5400, fn: (a) => { a.setNode(9, 'resolved'); a.setScore(94) } },
      { t: 5800, fn: (a) => { a.setNode(1, 'resolved'); a.setNode(2, 'resolved'); a.setNode(3, 'resolved') } },
      { t: 6200, fn: (a) => { a.setNode(0, 'resolved'); a.setScore(98); a.setStatus(STATUSES[3]) } },
    ]
    const LOOP_MS = 9000

    const api: TimelineApi = {
      setNode: (i, s) => {
        const n = nodes[i]
        n.state = s
        const m = n.mat
        const idleC = NODES[i].level === 0 ? COLOR_BRANCH_IDLE : COLOR_DIM
        if (s === 'dim') {
          m.color.copy(idleC); m.emissive.copy(idleC); m.emissiveIntensity = 0
          n.wireMat.color.set(0x9a8a70); n.wireMat.opacity = 0.35
          n.ringMat.opacity = 0
        }
        if (s === 'processing') {
          m.color.copy(COLOR_PROC); m.emissive.copy(COLOR_PROC); m.emissiveIntensity = 0.4
          n.wireMat.color.set(0xd7ba7d); n.wireMat.opacity = 0.85
          n.ringMat.color.set(0xd7ba7d); n.ringMat.opacity = 0.7
        }
        if (s === 'resolved') {
          m.color.copy(COLOR_RESOLVED); m.emissive.copy(COLOR_RESOLVED); m.emissiveIntensity = 0.25
          n.wireMat.color.set(0x86efac); n.wireMat.opacity = 0.6
          n.ringMat.color.set(0x86efac); n.ringMat.opacity = 0.4
        }
      },
      activateEdge: (i) => {
        const e = edges[i]
        if (!e) return
        e.targetOpacity = 0.45
        e.active = true
        e.mat.color.set(0xd7ba7d)
        if (!e.particle) {
          const pgeo = new THREE.SphereGeometry(0.04, 12, 12)
          const pmat = new THREE.MeshBasicMaterial({ color: 0xd7ba7d, transparent: true, opacity: 0.9 })
          const p = new THREE.Mesh(pgeo, pmat)
          root.add(p)
          disposables.push(pgeo, pmat)
          e.particle = p
          e.particleMat = pmat
        }
      },
      setScore: (n) => setScore(n),
      setStatus: (s) => setStatus(s),
      reset: () => {
        nodes.forEach((_, i) => api.setNode(i, 'dim'))
        edges.forEach((e) => {
          if (!e) return
          e.targetOpacity = 0.08
          e.active = false
          e.mat.color.set(0x9a8a70)
        })
        setScore(42)
      },
    }

    const start = performance.now()
    let lastStep = -1

    const animate = () => {
      frameRef.current = requestAnimationFrame(animate)
      if (!vis.current) return
      const now = performance.now()
      const elapsed = (now - start) % LOOP_MS

      // step trigger
      if (elapsed < 50 && lastStep > 0) lastStep = -1
      for (let i = 0; i < steps.length; i++) {
        if (elapsed >= steps[i].t && i > lastStep) {
          steps[i].fn(api)
          lastStep = i
        }
      }

      root.rotation.y += 0.0012

      // Pulse processing nodes
      const tt = now * 0.005
      nodes.forEach((n, i) => {
        // Counter-rotate wire shells so they spin independently of root
        n.wire.rotation.y += 0.012
        n.wire.rotation.x += 0.006
        // Keep rings facing camera
        n.ring.lookAt(camera.position)
        if (n.state === 'processing') {
          n.mat.emissiveIntensity = 0.3 + Math.sin(tt + i) * 0.18
          const s = 1 + Math.sin(tt * 1.5 + i) * 0.08
          n.ring.scale.setScalar(s)
        }
      })

      // Edge fade + particle
      edges.forEach((e) => {
        if (!e) return
        e.mat.opacity += (e.targetOpacity - e.mat.opacity) * 0.08
        if (e.active && e.particle) {
          e.particleT = (e.particleT + 0.012) % 1
          e.particle.position.lerpVectors(e.from, e.to, e.particleT)
          if (e.particleMat) e.particleMat.opacity = e.mat.opacity * 1.4
        } else if (e.particle && e.particleMat) {
          e.particleMat.opacity *= 0.9
        }
      })

      renderer.render(scene, camera)
    }
    animate()

    const onResize = () => {
      if (!el) return
      const nw = el.clientWidth
      const nh = el.clientHeight
      camera.aspect = nw / nh
      camera.updateProjectionMatrix()
      renderer.setSize(nw, nh)
    }
    window.addEventListener('resize', onResize)

    return () => {
      obs.disconnect()
      window.removeEventListener('resize', onResize)
      cancelAnimationFrame(frameRef.current)
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement)
      renderer.dispose()
      disposables.forEach((d) => d.dispose())
    }
  }, [])

  const scoreColor = score > 80 ? '#86efac' : score > 60 ? '#d7ba7d' : '#ce9178'

  return (
    <div
      className="relative w-full max-w-[860px] rounded-xl overflow-hidden mx-auto flex flex-col"
      style={{
        backgroundColor: '#0e0d0b',
        color: '#d4d4d4',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 40px 80px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04) inset',
      }}
    >
      {/* Header */}
      <div
        className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: 'rgba(255,255,255,0.08)' }}
      >
        <div className="flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span
            className="text-[11px] font-medium tracking-wide font-mono uppercase"
            style={{ color: '#e4ded2' }}
          >
            Agent Reasoning
          </span>
          <span
            className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono"
            style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}
          >
            n=10
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>3 levels</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span className="tabular-nums" style={{ color: scoreColor }}>{score}/100</span>
        </div>
      </div>

      {/* Canvas + grid bg */}
      <div className="relative flex-1">
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.08]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />
        <div ref={containerRef} className="relative w-full" style={{ height: 420 }} />
      </div>

      {/* Footer */}
      <div
        className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[8.5px]"
        style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <div className="flex items-center gap-3">
          <span style={{ color: '#6a737d' }}>Status</span>
          <span style={{ color: '#d7ba7d' }}>{status}</span>
        </div>
        <div className="flex items-center gap-3">
          <span style={{ color: '#6a737d' }}>Jurisdictions</span>
          <span className="tabular-nums" style={{ color: '#9a8a70' }}>CA · NY · FED · IL</span>
        </div>
      </div>
    </div>
  )
}
