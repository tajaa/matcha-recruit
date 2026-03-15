import { useEffect, useRef } from 'react'
import * as THREE from 'three'

interface CityMarker {
  label: string
  lat: number
  lon: number
}

const CITIES: CityMarker[] = [
  { label: 'LA', lat: 34.05, lon: -118.24 },
  { label: 'SF', lat: 37.77, lon: -122.42 },
  { label: 'NY', lat: 40.71, lon: -74.01 },
  { label: 'Austin', lat: 30.27, lon: -97.74 },
  { label: 'Miami', lat: 25.76, lon: -80.19 },
  { label: 'Chicago', lat: 41.88, lon: -87.63 },
  { label: 'Toronto', lat: 43.65, lon: -79.35 },
  { label: 'Mexico City', lat: 19.43, lon: -99.13 },
  { label: 'Bogota', lat: 4.71, lon: -74.07 },
  { label: 'Sao Paulo', lat: -23.55, lon: -46.63 },
  { label: 'Buenos Aires', lat: -34.60, lon: -58.38 },
  { label: 'Lima', lat: -12.05, lon: -77.04 },
  { label: 'London', lat: 51.51, lon: -0.13 },
  { label: 'Paris', lat: 48.86, lon: 2.35 },
  { label: 'Berlin', lat: 52.52, lon: 13.41 },
  { label: 'Lagos', lat: 6.52, lon: 3.38 },
  { label: 'Nairobi', lat: -1.29, lon: 36.82 },
  { label: 'Dubai', lat: 25.20, lon: 55.27 },
  { label: 'Mumbai', lat: 19.08, lon: 72.88 },
  { label: 'Tokyo', lat: 35.68, lon: 139.65 },
  { label: 'Singapore', lat: 1.35, lon: 103.82 },
  { label: 'Sydney', lat: -33.87, lon: 151.21 },
  { label: 'Seoul', lat: 37.57, lon: 126.98 },
  { label: 'Cape Town', lat: -33.92, lon: 18.42 },
]

function latLonToVec3(lat: number, lon: number, r: number) {
  const la = THREE.MathUtils.degToRad(lat)
  const lo = THREE.MathUtils.degToRad(lon)
  const c = Math.cos(la)
  return new THREE.Vector3(r * c * Math.sin(lo), r * Math.sin(la), r * c * Math.cos(lo))
}

function makeLabel(text: string) {
  const canvas = document.createElement('canvas')
  canvas.width = 600
  canvas.height = 160
  const ctx = canvas.getContext('2d')!
  const spaced = text.split('').join(' ').toUpperCase()
  ctx.clearRect(0, 0, 600, 160)
  ctx.font = '400 32px "Space Mono", monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.shadowColor = 'rgba(255,255,255,0.3)'
  ctx.shadowBlur = 8
  ctx.fillText(spaced, 300, 80)
  const tex = new THREE.CanvasTexture(canvas)
  tex.minFilter = THREE.LinearFilter
  tex.generateMipmaps = false
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.88 })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(0.68, 0.18, 1)
  return { sprite, mat, tex }
}

export default function ParticleSphere({ className = '' }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    el.querySelector('canvas')?.remove()

    const w = el.clientWidth
    const h = el.clientHeight
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000)
    camera.position.z = 2.5

    const group = new THREE.Group()
    const initX = THREE.MathUtils.degToRad(15)
    group.rotation.y = THREE.MathUtils.degToRad(70)
    group.rotation.x = initX
    scene.add(group)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setSize(w, h)
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)

    // Wireframe sphere
    const wireGeo = new THREE.SphereGeometry(1.3, 64, 64)
    const wireMat = new THREE.MeshBasicMaterial({ color: 0xa1a1aa, wireframe: true, transparent: true, opacity: 0.35 })
    group.add(new THREE.Mesh(wireGeo, wireMat))

    // City markers
    const dotGeo = new THREE.SphereGeometry(0.016, 16, 16)
    const pulseGeo = new THREE.SphereGeometry(0.028, 14, 14)
    const disposables: { dispose: () => void }[] = [wireGeo, wireMat, dotGeo, pulseGeo]

    type MI = { normal: THREE.Vector3; dotMat: THREE.MeshBasicMaterial; pulse: THREE.Mesh; pulseMat: THREE.MeshBasicMaterial; labelMat?: THREE.SpriteMaterial; lineMat?: THREE.LineBasicMaterial }
    const markers: MI[] = []

    CITIES.forEach((city, i) => {
      const n = latLonToVec3(city.lat, city.lon, 1.15).normalize()
      const pos = n.clone().multiplyScalar(1.18)

      const dotMat = new THREE.MeshBasicMaterial({ color: 0xb45309, transparent: true, opacity: 0.9 })
      const dot = new THREE.Mesh(dotGeo, dotMat)
      dot.position.copy(pos)
      group.add(dot)

      const pulseMat = new THREE.MeshBasicMaterial({ color: 0xd97706, transparent: true, opacity: 0.22 })
      const pulse = new THREE.Mesh(pulseGeo, pulseMat)
      pulse.position.copy(pos)
      pulse.scale.setScalar(1 + i * 0.02)
      group.add(pulse)

      const lineGeo = new THREE.BufferGeometry().setFromPoints([n.clone().multiplyScalar(1.2), n.clone().multiplyScalar(1.4)])
      const lineMat = new THREE.LineBasicMaterial({ color: 0xfafafa, transparent: true, opacity: 0.7 })
      group.add(new THREE.Line(lineGeo, lineMat))
      disposables.push(dotMat, pulseMat, lineGeo, lineMat)

      const label = makeLabel(city.label)
      label.sprite.position.copy(n.clone().multiplyScalar(1.45))
      group.add(label.sprite)
      disposables.push(label.mat, label.tex)

      markers.push({ normal: n.clone(), dotMat, pulse, pulseMat, labelMat: label.mat, lineMat })
    })

    // Visibility
    const vis = { current: true }
    const obs = new IntersectionObserver(([e]) => { vis.current = e.isIntersecting }, { rootMargin: '200px' })
    obs.observe(el)

    let t = 0
    const nw = new THREE.Vector3()
    const tc = new THREE.Vector3()

    const animate = () => {
      frameRef.current = requestAnimationFrame(animate)
      if (!vis.current) return
      t += 0.01
      group.rotation.y += 0.001
      group.rotation.x = initX + Math.sin(t * 0.2) * 0.05

      markers.forEach((m, i) => {
        m.pulse.scale.setScalar(1 + Math.sin(t * 2.2 + i) * 0.18)
        nw.copy(m.normal).applyQuaternion(group.quaternion).normalize()
        tc.copy(camera.position).normalize()
        const v = THREE.MathUtils.clamp((nw.dot(tc) - 0.05) / 0.35, 0, 1)
        m.dotMat.opacity = 0.22 + v * 0.75
        m.pulseMat.opacity = 0.06 + v * 0.24
        if (m.labelMat) m.labelMat.opacity = v
        if (m.lineMat) m.lineMat.opacity = v * 0.55
      })

      renderer.render(scene, camera)
    }
    animate()

    const onResize = () => {
      if (!el) return
      const nw2 = el.clientWidth
      const nh = el.clientHeight
      camera.aspect = nw2 / nh
      camera.updateProjectionMatrix()
      renderer.setSize(nw2, nh)
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

  return (
    <div ref={containerRef} className={`relative ${className}`} style={{ minHeight: 300 }}>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-10">
        <div className="relative">
          <div className="absolute w-8 h-px bg-zinc-500/50 -left-4 top-1/2" />
          <div className="absolute h-8 w-px bg-zinc-500/50 left-1/2 -top-4" />
          <div className="w-2 h-2 rounded-full bg-zinc-500 shadow-[0_0_10px_rgba(0,0,0,0.1)]" />
          <div className="absolute -top-6 -left-6 w-3 h-3 border-t border-l border-zinc-500/40" />
          <div className="absolute -top-6 -right-6 w-3 h-3 border-t border-r border-zinc-500/40" />
          <div className="absolute -bottom-6 -left-6 w-3 h-3 border-b border-l border-zinc-500/40" />
          <div className="absolute -bottom-6 -right-6 w-3 h-3 border-b border-r border-zinc-500/40" />
        </div>
      </div>
    </div>
  )
}
