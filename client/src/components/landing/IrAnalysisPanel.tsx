import { useEffect, useRef, useState } from 'react'
import { motion, useInView } from 'framer-motion'

// Shared Risk Insights mockup — used by the Platform landing page (Landing.tsx)
// and the distilled Matcha Lite page (MatchaLitePage.tsx). Source of truth lives
// here so the two surfaces never drift. Colors are intentionally hardcoded (dark
// dashboard chrome), independent of the ivory marketing tokens.
//
// It MOVES: stat numbers count up on view, a live "analysis scan" highlight
// travels down the risk matrix row-by-row, and the flagged (red) heat cells
// breathe a glow so the eye lands on the risk clusters.

type HeatLevel = 'red' | 'amber' | null

const RISK_MATRIX_ROWS: Array<{
  loc: string
  safety: { v: number; heat: HeatLevel }
  behavioral: { v: number; heat: HeatLevel }
  total: number
}> = [
  { loc: 'Hollywood', safety: { v: 11, heat: 'red' }, behavioral: { v: 3, heat: 'amber' }, total: 14 },
  { loc: 'Sherman Oaks', safety: { v: 11, heat: 'red' }, behavioral: { v: 1, heat: null }, total: 12 },
  { loc: 'Beverly Hills', safety: { v: 10, heat: 'red' }, behavioral: { v: 2, heat: 'amber' }, total: 12 },
  { loc: 'San Diego', safety: { v: 5, heat: null }, behavioral: { v: 1, heat: null }, total: 6 },
]

const MATRIX_COLS = '1fr 52px 70px 52px 60px 44px 40px'

// count-up easing toward target while `run` is true
function useCountUp(target: number, run: boolean, duration = 1100) {
  const [v, setV] = useState(0)
  const raf = useRef(0)
  const start = useRef(0)
  useEffect(() => {
    if (!run) { setV(0); start.current = 0; return }
    const tick = (now: number) => {
      if (!start.current) start.current = now
      const t = Math.min(1, (now - start.current) / duration)
      setV(Math.round((1 - Math.pow(1 - t, 3)) * target))
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf.current); start.current = 0 }
  }, [target, run, duration])
  return v
}

export function IrAnalysisPanel() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-40px' })

  // traveling analysis scan over the matrix rows (+ a brief "rest" frame)
  const [scan, setScan] = useState(-1)
  useEffect(() => {
    if (!inView) { setScan(-1); return }
    let i = 0
    const steps = RISK_MATRIX_ROWS.length + 1 // last step = no row highlighted
    const id = setInterval(() => {
      const s = i % steps
      setScan(s < RISK_MATRIX_ROWS.length ? s : -1)
      i++
    }, 1000)
    return () => clearInterval(id)
  }, [inView])

  const total = useCountUp(57, inView, 1200)
  const cats = [
    { label: 'Safety', count: 43, sev: '3.0' },
    { label: 'Behavioral', count: 12, sev: '1.8' },
    { label: 'Property', count: 0, sev: null },
    { label: 'Near Miss', count: 0, sev: null },
    { label: 'Other', count: 2, sev: '2.0' },
  ]

  return (
    <div ref={ref} className="rounded-xl overflow-x-auto border font-sans" style={{ borderColor: 'rgba(63,63,70,0.5)', backgroundColor: '#0d0d10' }}>
    <div className="min-w-[520px]">
      {/* Page header */}
      <div className="flex items-start justify-between px-5 py-4 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold" style={{ color: '#f4f4f5' }}>Risk Insights</span>
            <motion.span
              className="px-1.5 py-0.5 rounded text-[8px] font-medium"
              style={{ backgroundColor: 'rgba(16,185,129,0.15)', color: '#6ee7b7', border: '1px solid rgba(16,185,129,0.25)' }}
              animate={inView ? { opacity: [1, 0.4, 1] } : {}}
              transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
            >
              LIVE
            </motion.span>
          </div>
          <div className="text-[8px] uppercase tracking-widest mt-1" style={{ color: '#52525b' }}>Computed May 24, 2026 at 2:06 am</div>
        </div>
        <div className="flex items-center gap-1.5">
          {(['All locations', 'Last 90 days'] as const).map(label => (
            <div key={label} className="flex items-center gap-1 px-2 py-1 rounded" style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#71717a', fontSize: 8 }}>
              {label} <span style={{ fontSize: 7 }}>▾</span>
            </div>
          ))}
        </div>
      </div>

      {/* Stat row */}
      <div className="grid border-b" style={{ gridTemplateColumns: '1.5fr 1fr 1fr 1fr 1fr 1fr', borderColor: 'rgba(39,39,42,0.5)' }}>
        <div className="px-4 py-4 border-r" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
          <div className="text-[7px] uppercase tracking-widest mb-3" style={{ color: '#52525b' }}>Incidents · Last 90 days</div>
          <div className="leading-none font-bold tabular-nums" style={{ fontSize: '2.5rem', color: '#fff', letterSpacing: '-0.03em' }}>
            {total}
          </div>
          <div className="text-[7px] mt-3 flex items-center gap-1" style={{ color: '#2f9e74' }}>
            <motion.span className="inline-block w-1 h-1 rounded-full" style={{ backgroundColor: '#2f9e74' }}
              animate={inView ? { opacity: [1, 0.2, 1] } : {}} transition={{ duration: 1.4, repeat: Infinity }} />
            Analyzing 7 locations · 3 flagged
          </div>
        </div>
        {cats.map((cat, i) => (
          <motion.div
            key={cat.label}
            initial={{ opacity: 0, y: 6 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.08 + i * 0.06 }}
            className={`px-3 py-4 ${i < 4 ? 'border-r' : ''}`}
            style={{ borderColor: 'rgba(39,39,42,0.5)' }}
          >
            <div className="text-[7px] uppercase tracking-widest mb-3" style={{ color: '#52525b' }}>{cat.label}</div>
            <div className="leading-none font-bold tabular-nums" style={{ fontSize: '1.6rem', color: cat.count > 0 ? '#f4f4f5' : '#27272a', letterSpacing: '-0.02em' }}>
              <CatCount target={cat.count} run={inView} />
            </div>
            <div className="text-[7px] mt-3 uppercase tracking-wider" style={{ color: '#3f3f46' }}>
              {cat.sev ? `Avg sev ${cat.sev}` : 'None'}
            </div>
          </motion.div>
        ))}
      </div>

      {/* Risk matrix */}
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <span className="text-[7px] uppercase tracking-widest" style={{ color: '#52525b' }}>Risk Matrix · Last 90 days</span>
        <span className="text-[7px] tabular-nums" style={{ color: '#52525b' }}>{total} incidents · 7 locations</span>
      </div>
      <div className="grid px-2" style={{ gridTemplateColumns: MATRIX_COLS, backgroundColor: '#141418' }}>
        {([['Location', 'left'], ['Safety', 'center'], ['Behavioral', 'center'], ['Property', 'center'], ['Near Miss', 'center'], ['Other', 'center'], ['Total', 'center']] as [string, string][]).map(([h, align]) => (
          <div key={h} className="px-1.5 py-1.5 text-[7px] font-bold uppercase tracking-wider" style={{ color: '#52525b', textAlign: align as 'left' | 'center' }}>{h}</div>
        ))}
      </div>
      {RISK_MATRIX_ROWS.map((row, i) => {
        const scanned = scan === i
        return (
          <motion.div
            key={row.loc}
            initial={{ opacity: 0, x: -8 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: 0.25 + i * 0.07 }}
            className="grid border-t px-2 relative"
            style={{ gridTemplateColumns: MATRIX_COLS, borderColor: 'rgba(39,39,42,0.4)' }}
          >
            <motion.div
              className="absolute inset-0 pointer-events-none"
              animate={{ opacity: scanned ? 1 : 0 }}
              transition={{ duration: 0.4 }}
              style={{ background: 'linear-gradient(90deg, rgba(110,231,183,0.10) 0%, rgba(110,231,183,0.02) 60%, transparent 100%)', boxShadow: 'inset 2px 0 0 #2f9e74' }}
            />
            <div className="px-1.5 py-2 text-[10px] relative" style={{ color: scanned ? '#f4f4f5' : '#d4d4d8', transition: 'color 0.3s' }}>{row.loc}</div>
            <MatrixCell v={row.safety.v} heat={row.safety.heat} inView={inView} />
            <MatrixCell v={row.behavioral.v} heat={row.behavioral.heat} inView={inView} />
            <MatrixCell v={null} heat={null} inView={inView} />
            <MatrixCell v={null} heat={null} inView={inView} />
            <MatrixCell v={null} heat={null} inView={inView} />
            <div className="py-2 text-center text-[10px] relative tabular-nums" style={{ color: '#a1a1aa' }}>{row.total}</div>
          </motion.div>
        )
      })}
      <div className="grid border-t px-2" style={{ gridTemplateColumns: MATRIX_COLS, borderColor: 'rgba(63,63,70,0.6)', backgroundColor: '#141418' }}>
        <div className="px-1.5 py-2 text-[7px] uppercase tracking-wider" style={{ color: '#52525b' }}>Company Total</div>
        {[43, 12, 0, 0, 2, 57].map((v, i) => (
          <div key={i} className="py-2 text-center text-[10px] tabular-nums" style={{ color: i === 5 ? '#f4f4f5' : v === 0 ? '#52525b' : '#a1a1aa', fontWeight: i === 5 ? 600 : 400 }}>{v}</div>
        ))}
      </div>
      <div className="flex items-center gap-4 px-4 py-2.5 border-t" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        {[
          { color: 'rgba(181,74,63,0.45)', label: 'Flagged ≥2× baseline' },
          { color: 'rgba(201,138,62,0.4)', label: 'Above baseline' },
          { color: '#27272a', label: 'At/below baseline' },
        ].map(l => (
          <div key={l.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: l.color, border: '1px solid rgba(255,255,255,0.08)' }} />
            <span className="text-[7px]" style={{ color: '#52525b' }}>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
    </div>
  )
}

function CatCount({ target, run }: { target: number; run: boolean }) {
  const v = useCountUp(target, run, 900)
  return <>{target > 0 ? v : 0}</>
}

function MatrixCell({ v, heat, inView }: { v: number | null; heat: HeatLevel; inView: boolean }) {
  if (!v) return <div className="py-2 text-center text-[9px] relative" style={{ color: '#3f3f46' }}>—</div>
  const bg = heat === 'red' ? 'rgba(181,74,63,0.32)' : heat === 'amber' ? 'rgba(201,138,62,0.28)' : 'transparent'
  const color = heat === 'red' ? '#e8a99f' : heat === 'amber' ? '#c98a3e' : '#a1a1aa'
  return (
    <motion.div
      className="py-2 text-center relative"
      style={{ backgroundColor: bg }}
      animate={heat === 'red' && inView ? { boxShadow: ['inset 0 0 0 rgba(206,90,79,0)', 'inset 0 0 14px rgba(206,90,79,0.45)', 'inset 0 0 0 rgba(206,90,79,0)'] } : {}}
      transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
    >
      <span className="text-[10px] font-medium tabular-nums" style={{ color }}>{v}</span>
    </motion.div>
  )
}
