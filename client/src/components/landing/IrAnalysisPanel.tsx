import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'

// Shared Risk Insights mockup — used by the Platform landing page (Landing.tsx)
// and the distilled Matcha Lite page (MatchaLitePage.tsx). Source of truth lives
// here so the two surfaces never drift. Colors are intentionally hardcoded (dark
// dashboard chrome), independent of the ivory marketing tokens.

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

export function IrAnalysisPanel() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })

  return (
    <div ref={ref} className="rounded-xl overflow-x-auto border font-sans" style={{ borderColor: 'rgba(63,63,70,0.5)', backgroundColor: '#0d0d10' }}>
    <div className="min-w-[520px]">
      {/* Page header */}
      <div className="flex items-start justify-between px-5 py-4 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <div>
          <div className="text-sm font-bold" style={{ color: '#f4f4f5' }}>Risk Insights</div>
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
          <motion.div
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            className="leading-none font-bold"
            style={{ fontSize: '2.5rem', color: '#fff', letterSpacing: '-0.03em' }}
          >
            57
          </motion.div>
          <div className="text-[7px] mt-3" style={{ color: '#3f3f46' }}>⚡ No flagged locations or critical patterns</div>
        </div>
        {[
          { label: 'Safety', count: 43, sev: '3.0' },
          { label: 'Behavioral', count: 12, sev: '1.8' },
          { label: 'Property', count: 0, sev: null },
          { label: 'Near Miss', count: 0, sev: null },
          { label: 'Other', count: 2, sev: '2.0' },
        ].map((cat, i) => (
          <motion.div
            key={cat.label}
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ delay: 0.08 + i * 0.06 }}
            className={`px-3 py-4 ${i < 4 ? 'border-r' : ''}`}
            style={{ borderColor: 'rgba(39,39,42,0.5)' }}
          >
            <div className="text-[7px] uppercase tracking-widest mb-3" style={{ color: '#52525b' }}>{cat.label}</div>
            <div className="leading-none font-bold" style={{ fontSize: '1.6rem', color: cat.count > 0 ? '#f4f4f5' : '#27272a', letterSpacing: '-0.02em' }}>
              {cat.count}
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
        <span className="text-[7px]" style={{ color: '#52525b' }}>57 incidents · 7 locations</span>
      </div>
      <div className="grid px-2" style={{ gridTemplateColumns: '1fr 52px 70px 52px 60px 44px 40px', backgroundColor: '#141418' }}>
        {([['Location', 'left'], ['Safety', 'center'], ['Behavioral', 'center'], ['Property', 'center'], ['Near Miss', 'center'], ['Other', 'center'], ['Total', 'center']] as [string, string][]).map(([h, align]) => (
          <div key={h} className="px-1.5 py-1.5 text-[7px] font-bold uppercase tracking-wider" style={{ color: '#52525b', textAlign: align as 'left' | 'center' }}>{h}</div>
        ))}
      </div>
      {RISK_MATRIX_ROWS.map((row, i) => (
        <motion.div
          key={row.loc}
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ delay: 0.25 + i * 0.07 }}
          className="grid border-t px-2"
          style={{ gridTemplateColumns: '1fr 52px 70px 52px 60px 44px 40px', borderColor: 'rgba(39,39,42,0.4)' }}
        >
          <div className="px-1.5 py-2 text-[10px]" style={{ color: '#d4d4d8' }}>{row.loc}</div>
          <MatrixCell v={row.safety.v} heat={row.safety.heat} />
          <MatrixCell v={row.behavioral.v} heat={row.behavioral.heat} />
          <MatrixCell v={null} heat={null} />
          <MatrixCell v={null} heat={null} />
          <MatrixCell v={null} heat={null} />
          <div className="py-2 text-center text-[10px]" style={{ color: '#a1a1aa' }}>{row.total}</div>
        </motion.div>
      ))}
      <div className="grid border-t px-2" style={{ gridTemplateColumns: '1fr 52px 70px 52px 60px 44px 40px', borderColor: 'rgba(63,63,70,0.6)', backgroundColor: '#141418' }}>
        <div className="px-1.5 py-2 text-[7px] uppercase tracking-wider" style={{ color: '#52525b' }}>Company Total</div>
        {[43, 12, 0, 0, 2, 57].map((v, i) => (
          <div key={i} className="py-2 text-center text-[10px]" style={{ color: i === 5 ? '#f4f4f5' : v === 0 ? '#52525b' : '#a1a1aa', fontWeight: i === 5 ? 600 : 400 }}>{v}</div>
        ))}
      </div>
      <div className="flex items-center gap-4 px-4 py-2.5 border-t" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        {[
          { color: 'rgba(127,29,29,0.7)', label: 'Flagged ≥2× baseline' },
          { color: 'rgba(120,53,15,0.7)', label: 'Above baseline' },
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

function MatrixCell({ v, heat }: { v: number | null; heat: HeatLevel }) {
  if (!v) return <div className="py-2 text-center text-[9px]" style={{ color: '#3f3f46' }}>—</div>
  const bg = heat === 'red' ? 'rgba(127,29,29,0.5)' : heat === 'amber' ? 'rgba(120,53,15,0.5)' : 'transparent'
  const color = heat === 'red' ? '#fca5a5' : heat === 'amber' ? '#fbbf24' : '#a1a1aa'
  return (
    <div className="py-2 text-center" style={{ backgroundColor: bg }}>
      <span className="text-[10px] font-medium" style={{ color }}>{v}</span>
    </div>
  )
}
