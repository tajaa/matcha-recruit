import { lazy, Suspense, useEffect, useState, useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { LinkButton } from '../components/ui'
import { AsciiHalftone } from '../components/AsciiHalftone'
import { GlitchText } from '../components/GlitchText'
import { PricingContactModal } from '../components/PricingContactModal'

const ParticleSphere = lazy(() => import('../components/ParticleSphere'))

/* ── Shared CSS for animated graphics ─────────────────────────── */
const SCAN_LINE_BG = 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(161,161,170,0.03) 2px, rgba(161,161,170,0.03) 4px)'
const DOT_GRID_BG = 'radial-gradient(circle, rgba(161,161,170,0.4) 1px, transparent 1px)'

/* ── Pre-computed static waveforms for SignalMonitor ──────────── */
const _wave = (freq: number, amp: number, phase: number) =>
  Array.from({ length: 80 }, (_, i) => {
    const x = (i / 79) * 100
    const y = 50 + Math.sin((i / 79) * Math.PI * freq + phase) * amp
    return `${x},${y}`
  }).join(' ')
const SIGNAL_WAVE_1 = _wave(4, 15, 0)
const SIGNAL_WAVE_2 = _wave(6, 8, 1.5)
const SIGNAL_WAVE_3 = _wave(2.5, 20, 3)

/* ── Static data for PatternGrid & RadarChart ────────────────── */
const PATTERN_INCIDENTS = new Set([12, 23, 34, 45, 52, 63, 33, 22])
const RADAR_DIMS = ['Legal', 'Compliance', 'Tenure', 'Performance', 'Protected Class', 'Documentation', 'Precedent', 'Timing', 'Org Impact']
const RADAR_VALUES = [0.7, 0.9, 0.4, 0.6, 0.85, 0.3, 0.5, 0.75, 0.65]

/* ── Jurisdiction Cascade (Compliance Engine) ─────────────────── */
function JurisdictionCascade() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const tiers = [
    { level: 'FEDERAL', items: ['FLSA', 'OSHA', 'FMLA', 'ADA', 'EEOC'] },
    { level: 'STATE', items: ['CA FEHA', 'NY WARN', 'TX TWC', 'FL SB', 'WA PFML'] },
    { level: 'LOCAL', items: ['SF HCSO', 'NYC ESL', 'LA MWO', 'SEA PSL', 'CHI FWW'] },
  ]
  return (
    <div ref={ref} className="relative h-72 lg:h-80 overflow-hidden" style={{ backgroundImage: SCAN_LINE_BG }}>
      {/* Connecting lines */}
      <svg className="absolute inset-0 w-full h-full" style={{ opacity: inView ? 0.3 : 0 }}>
        <line x1="50%" y1="28%" x2="30%" y2="52%" stroke="#10b981" strokeWidth="1" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </line>
        <line x1="50%" y1="28%" x2="70%" y2="52%" stroke="#10b981" strokeWidth="1" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
        </line>
        <line x1="30%" y1="58%" x2="25%" y2="78%" stroke="#10b981" strokeWidth="1" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1.2s" repeatCount="indefinite" />
        </line>
        <line x1="70%" y1="58%" x2="75%" y2="78%" stroke="#10b981" strokeWidth="1" strokeDasharray="4 4">
          <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1.2s" repeatCount="indefinite" />
        </line>
      </svg>

      {tiers.map((tier, ti) => (
        <div
          key={tier.level}
          className="absolute left-0 right-0 flex flex-col items-center"
          style={{ top: `${ti * 32 + 4}%` }}
        >
          <span
            className="text-[9px] tracking-[0.3em] font-[Space_Mono] uppercase mb-2 transition-all duration-700"
            style={{
              color: ti === 0 ? '#10b981' : ti === 1 ? '#34d399' : '#6ee7b7',
              opacity: inView ? 1 : 0,
              transform: inView ? 'translateY(0)' : 'translateY(-8px)',
              transitionDelay: `${ti * 300}ms`,
            }}
          >
            {tier.level}
          </span>
          <div className="flex gap-2 flex-wrap justify-center">
            {tier.items.map((item, ii) => (
              <span
                key={item}
                className="px-2.5 py-1 border text-[9px] font-[Space_Mono] tracking-wider transition-all duration-500"
                style={{
                  borderColor: inView ? (ti === 0 ? '#10b981' : '#3f3f46') : 'transparent',
                  color: inView ? '#a1a1aa' : 'transparent',
                  opacity: inView ? 1 : 0,
                  transform: inView ? 'translateY(0) scale(1)' : 'translateY(12px) scale(0.9)',
                  transitionDelay: `${ti * 300 + ii * 80}ms`,
                  background: ti === 0 && ii === 2 ? 'rgba(16,185,129,0.08)' : 'transparent',
                  boxShadow: ti === 0 && ii === 2 ? '0 0 12px rgba(16,185,129,0.15)' : 'none',
                }}
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      ))}

      {/* Pulse indicator */}
      <div className="absolute top-3 right-3 flex items-center gap-1.5">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span className="text-[8px] font-[Space_Mono] text-emerald-500/60 uppercase tracking-widest">Live</span>
      </div>
    </div>
  )
}

/* ── Signal Monitor (Legislative Tracker) ─────────────────────── */
function SignalMonitor() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const [scanX, setScanX] = useState(0)

  useEffect(() => {
    if (!inView) return
    let raf: number
    const animate = () => {
      setScanX(prev => (prev + 0.3) % 100)
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [inView])

  return (
    <div ref={ref} className="relative h-72 lg:h-80 overflow-hidden" style={{ backgroundImage: SCAN_LINE_BG }}>
      <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {/* Background grid */}
        {[20, 40, 60, 80].map(y => (
          <line key={`h${y}`} x1="0" y1={y} x2="100" y2={y} stroke="#3f3f46" strokeWidth="0.15" />
        ))}
        {[20, 40, 60, 80].map(x => (
          <line key={`v${x}`} x1={x} y1="0" x2={x} y2="100" stroke="#3f3f46" strokeWidth="0.15" />
        ))}

        {/* Waveforms */}
        <polyline
          points={SIGNAL_WAVE_1}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="0.4"
          opacity={inView ? 0.6 : 0}
          style={{ transition: 'opacity 1s' }}
        >
          <animateTransform attributeName="transform" type="translate" from="-2,0" to="2,0" dur="3s" repeatCount="indefinite" />
        </polyline>
        <polyline
          points={SIGNAL_WAVE_2}
          fill="none"
          stroke="#d97706"
          strokeWidth="0.3"
          opacity={inView ? 0.35 : 0}
          style={{ transition: 'opacity 1.2s' }}
        >
          <animateTransform attributeName="transform" type="translate" from="1,0" to="-1,0" dur="4s" repeatCount="indefinite" />
        </polyline>
        <polyline
          points={SIGNAL_WAVE_3}
          fill="none"
          stroke="#fbbf24"
          strokeWidth="0.25"
          opacity={inView ? 0.2 : 0}
          style={{ transition: 'opacity 1.5s' }}
        >
          <animateTransform attributeName="transform" type="translate" from="-1,0" to="1,0" dur="5s" repeatCount="indefinite" />
        </polyline>

        {/* Scanline */}
        <line
          x1={scanX} y1="0" x2={scanX} y2="100"
          stroke="#f59e0b" strokeWidth="0.3" opacity="0.5"
        />
        <circle cx={scanX} cy={50 + Math.sin(scanX * 0.15) * 15} r="1.2" fill="#f59e0b" opacity="0.8">
          <animate attributeName="r" values="1.2;2;1.2" dur="0.8s" repeatCount="indefinite" />
        </circle>

        {/* Alert blips */}
        {[25, 58, 82].map((x, i) => (
          <g key={i}>
            <circle cx={x} cy={50 + Math.sin(x * 0.2 + i) * 12} r="0.8" fill="#f59e0b" opacity="0.9">
              <animate attributeName="opacity" values="0.9;0.3;0.9" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
            </circle>
            <circle cx={x} cy={50 + Math.sin(x * 0.2 + i) * 12} r="2.5" fill="none" stroke="#f59e0b" strokeWidth="0.2" opacity="0.3">
              <animate attributeName="r" values="2.5;5;2.5" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.3;0;0.3" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
            </circle>
          </g>
        ))}
      </svg>

      <div className="absolute bottom-3 left-3 text-[8px] font-[Space_Mono] text-amber-500/50 tracking-widest uppercase">
        Regulatory Signal // {inView ? 'Monitoring' : 'Standby'}
      </div>
    </div>
  )
}

/* ── Monte Carlo Distribution (Risk Assessment) ──────────────── */
function MonteCarloDistribution() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const barCount = 24
  const heights = Array.from({ length: barCount }, (_, i) => {
    const x = (i - barCount / 2) / (barCount / 4)
    return Math.exp(-0.5 * x * x) * 100
  })
  const maxH = Math.max(...heights)

  return (
    <div ref={ref} className="relative h-72 lg:h-80 overflow-hidden flex items-end justify-center gap-[3px] px-8 pb-10 pt-6"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      {/* Threshold line */}
      <div
        className="absolute left-0 right-0 border-t border-dashed transition-opacity duration-1000"
        style={{
          top: '28%',
          borderColor: 'rgba(239,68,68,0.4)',
          opacity: inView ? 1 : 0,
          transitionDelay: '1.2s',
        }}
      >
        <span className="absolute right-2 -top-4 text-[8px] font-[Space_Mono] text-red-400/60 uppercase tracking-wider">
          Critical Threshold
        </span>
      </div>

      {heights.map((h, i) => {
        const pct = (h / maxH) * 70
        const hue = pct > 55 ? 0 : pct > 35 ? 38 : 160
        return (
          <div
            key={i}
            className="flex-1 max-w-3 transition-all rounded-t-[1px]"
            style={{
              height: inView ? `${pct}%` : '0%',
              background: `hsl(${hue}, 70%, ${45 + (pct / 70) * 15}%)`,
              opacity: inView ? 0.85 : 0,
              transitionDuration: '800ms',
              transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
              transitionDelay: `${i * 40 + 200}ms`,
              boxShadow: pct > 55 ? `0 0 8px hsla(${hue}, 70%, 50%, 0.3)` : 'none',
            }}
          />
        )
      })}

      {/* Axis labels */}
      <div className="absolute bottom-2 left-8 right-8 flex justify-between text-[7px] font-[Space_Mono] text-zinc-600">
        <span>$0</span>
        <span>ANNUAL LOSS EXPOSURE</span>
        <span>$5M+</span>
      </div>

      {/* Stats overlay */}
      <div
        className="absolute top-3 left-3 flex flex-col gap-1 transition-opacity duration-700"
        style={{ opacity: inView ? 1 : 0, transitionDelay: '1.5s' }}
      >
        <span className="text-[8px] font-[Space_Mono] text-emerald-500/70 tracking-wider">P50: $142,000</span>
        <span className="text-[8px] font-[Space_Mono] text-amber-500/70 tracking-wider">P90: $890,000</span>
        <span className="text-[8px] font-[Space_Mono] text-red-400/70 tracking-wider">P99: $2.4M</span>
      </div>
    </div>
  )
}

/* ── Timeline Constructor (ER Copilot) ────────────────────────── */
function TimelineConstructor() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const nodes = [
    { label: 'Complaint Filed', status: 'complete' },
    { label: 'Docs Analyzed', status: 'complete' },
    { label: 'Discrepancy Found', status: 'alert' },
    { label: 'Report Generated', status: 'complete' },
  ]

  return (
    <div ref={ref} className="relative h-72 lg:h-80 flex items-center overflow-hidden px-4"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      <div className="w-full">
        {/* Main timeline line */}
        <div className="relative mx-8">
          <div
            className="absolute top-1/2 left-0 h-px bg-gradient-to-r from-amber-500/60 via-amber-500/40 to-zinc-700 transition-all duration-1500"
            style={{
              width: inView ? '100%' : '0%',
              transitionDuration: '2s',
              transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          />

          <div className="relative flex justify-between">
            {nodes.map((node, i) => (
              <div
                key={i}
                className="flex flex-col items-center gap-3 transition-all"
                style={{
                  opacity: inView ? 1 : 0,
                  transform: inView ? 'translateY(0)' : 'translateY(16px)',
                  transitionDuration: '600ms',
                  transitionDelay: `${i * 400 + 400}ms`,
                }}
              >
                <span className="text-[8px] font-[Space_Mono] text-zinc-500 uppercase tracking-wider text-center w-20">
                  {node.label}
                </span>
                <div className="relative">
                  <div
                    className={`h-4 w-4 rounded-full border-2 ${
                      node.status === 'alert'
                        ? 'border-amber-500 bg-amber-500/20'
                        : 'border-zinc-500 bg-zinc-800'
                    }`}
                  />
                  {node.status === 'alert' && (
                    <div className="absolute inset-0 rounded-full border-2 border-amber-500 animate-ping opacity-30" />
                  )}
                </div>
                <span
                  className="text-[7px] font-[Space_Mono] uppercase tracking-wider"
                  style={{ color: node.status === 'alert' ? '#f59e0b' : '#52525b' }}
                >
                  {node.status === 'alert' ? '! FLAGGED' : 'VERIFIED'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Animated document scan */}
        <div
          className="mt-8 mx-8 flex gap-3 transition-opacity duration-700"
          style={{ opacity: inView ? 1 : 0, transitionDelay: '2s' }}
        >
          {['policy_doc.pdf', 'witness_stmt.docx', 'email_chain.eml'].map((doc, i) => (
            <div key={doc} className="flex items-center gap-1.5 px-2 py-1 border border-zinc-800 bg-zinc-900/80">
              <div className="h-1 w-1 rounded-full bg-amber-500" style={{ animation: `pulse 2s ${i * 0.4}s infinite` }} />
              <span className="text-[7px] font-[Space_Mono] text-zinc-500">{doc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Pattern Grid (Incident Reports) ──────────────────────────── */
function PatternGrid() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const rows = 7
  const cols = 10
  const epicenter = 33

  return (
    <div ref={ref} className="relative h-72 lg:h-80 flex items-center justify-center overflow-hidden"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
        {Array.from({ length: rows * cols }, (_, i) => {
          const row = Math.floor(i / cols)
          const col = i % cols
          const epicRow = Math.floor(epicenter / cols)
          const epicCol = epicenter % cols
          const dist = Math.sqrt((row - epicRow) ** 2 + (col - epicCol) ** 2)
          const isIncident = PATTERN_INCIDENTS.has(i)

          return (
            <div
              key={i}
              className="relative h-3 w-3 rounded-full transition-all"
              style={{
                backgroundColor: isIncident
                  ? inView ? '#f59e0b' : '#27272a'
                  : inView ? '#3f3f46' : '#27272a',
                opacity: inView ? 1 : 0,
                transform: inView ? 'scale(1)' : 'scale(0)',
                transitionDuration: '500ms',
                transitionDelay: `${dist * 80 + 200}ms`,
                boxShadow: isIncident && inView ? '0 0 8px rgba(245,158,11,0.4)' : 'none',
                animation: isIncident && inView ? `pulse 2.5s ${dist * 0.15}s infinite` : 'none',
              }}
            />
          )
        })}
      </div>

      {/* Ripple rings from epicenter */}
      {inView && [1, 2, 3].map(ring => (
        <div
          key={ring}
          className="absolute rounded-full border border-amber-500/20 pointer-events-none"
          style={{
            width: `${ring * 80}px`,
            height: `${ring * 80}px`,
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            animation: `ripple-expand 3s ${ring * 0.6}s infinite`,
          }}
        />
      ))}

      <div className="absolute bottom-3 right-3 text-[8px] font-[Space_Mono] text-amber-500/50 uppercase tracking-widest">
        {PATTERN_INCIDENTS.size} Incidents // Pattern Detected
      </div>
    </div>
  )
}

/* ── 9-Dimension Radar (Pre-Termination Intel) ────────────────── */
function RadarChart() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const cx = 50, cy = 50, r = 35

  const toXY = (angle: number, radius: number) => ({
    x: cx + Math.cos(angle - Math.PI / 2) * radius,
    y: cy + Math.sin(angle - Math.PI / 2) * radius,
  })

  const polygon = RADAR_VALUES.map((v, i) => {
    const angle = (i / RADAR_DIMS.length) * Math.PI * 2
    const p = toXY(angle, r * v)
    return `${p.x},${p.y}`
  }).join(' ')

  return (
    <div ref={ref} className="relative h-72 lg:h-80 flex items-center justify-center overflow-hidden"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      <svg viewBox="0 0 100 100" className="w-64 h-64 lg:w-72 lg:h-72">
        {/* Concentric rings */}
        {[0.25, 0.5, 0.75, 1].map(scale => (
          <polygon
            key={scale}
            points={RADAR_DIMS.map((_, i) => {
              const a = (i / RADAR_DIMS.length) * Math.PI * 2
              const p = toXY(a, r * scale)
              return `${p.x},${p.y}`
            }).join(' ')}
            fill="none"
            stroke="#3f3f46"
            strokeWidth="0.3"
          />
        ))}

        {/* Axes */}
        {RADAR_DIMS.map((_, i) => {
          const a = (i / RADAR_DIMS.length) * Math.PI * 2
          const p = toXY(a, r)
          return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="#3f3f46" strokeWidth="0.2" />
        })}

        {/* Data polygon */}
        <polygon
          points={polygon}
          fill="rgba(245,158,11,0.1)"
          stroke="#f59e0b"
          strokeWidth="0.6"
          strokeLinejoin="round"
          style={{
            opacity: inView ? 1 : 0,
            transition: 'opacity 1.2s ease',
            transitionDelay: '0.3s',
          }}
        >
          <animate attributeName="stroke-opacity" values="1;0.5;1" dur="3s" repeatCount="indefinite" />
        </polygon>

        {/* Data points */}
        {RADAR_VALUES.map((v, i) => {
          const a = (i / RADAR_DIMS.length) * Math.PI * 2
          const p = toXY(a, r * v)
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r="1"
              fill={v > 0.7 ? '#ef4444' : '#f59e0b'}
              style={{
                opacity: inView ? 1 : 0,
                transition: 'opacity 0.5s',
                transitionDelay: `${i * 100 + 800}ms`,
              }}
            >
              {v > 0.7 && <animate attributeName="r" values="1;1.8;1" dur="2s" repeatCount="indefinite" />}
            </circle>
          )
        })}

        {/* Labels */}
        {RADAR_DIMS.map((label, i) => {
          const a = (i / RADAR_DIMS.length) * Math.PI * 2
          const p = toXY(a, r + 8)
          return (
            <text
              key={label}
              x={p.x}
              y={p.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="font-[Space_Mono]"
              style={{
                fontSize: '2.5px',
                fill: RADAR_VALUES[i] > 0.7 ? '#ef4444' : '#71717a',
                opacity: inView ? 1 : 0,
                transition: 'opacity 0.5s',
                transitionDelay: `${i * 100 + 600}ms`,
              }}
            >
              {label}
            </text>
          )
        })}
      </svg>

      {/* Risk score */}
      <div
        className="absolute top-3 right-3 text-right transition-opacity duration-700"
        style={{ opacity: inView ? 1 : 0, transitionDelay: '1.5s' }}
      >
        <div className="text-[8px] font-[Space_Mono] text-zinc-500 uppercase tracking-wider">Risk Score</div>
        <div className="text-lg font-[Orbitron] font-bold text-amber-500">72</div>
        <div className="text-[8px] font-[Space_Mono] text-red-400/60 uppercase">HIGH</div>
      </div>
    </div>
  )
}

/* ── Typing Terminal (Matcha Work) ────────────────────────────── */
function TerminalTyping() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [queryIdx, setQueryIdx] = useState(0)
  const [responseIdx, setResponseIdx] = useState(0)
  const t3Ref = useRef<ReturnType<typeof setInterval> | null>(null)
  const query = '> What are the overtime exemption requirements for salaried employees in California vs. federal FLSA?'
  const response = 'Analyzing federal FLSA § 13(a)(1) against CA Labor Code § 515... California applies a stricter salary threshold ($66,560/yr vs federal $35,568). The duties test also diverges: CA requires >50% time on exempt duties while federal uses the primary duty test. Recommendation: Apply CA standard for all CA-based employees.'

  useEffect(() => {
    if (!inView) return
    const t1 = setInterval(() => {
      setQueryIdx(prev => {
        if (prev >= query.length) { clearInterval(t1); return prev }
        return prev + 1
      })
    }, 35)
    const t2 = setTimeout(() => {
      t3Ref.current = setInterval(() => {
        setResponseIdx(prev => {
          if (prev >= response.length) { clearInterval(t3Ref.current!); t3Ref.current = null; return prev }
          return prev + 2
        })
      }, 15)
    }, query.length * 35 + 500)
    return () => { clearInterval(t1); clearTimeout(t2); if (t3Ref.current) clearInterval(t3Ref.current) }
  }, [inView])

  return (
    <div ref={ref} className="max-w-2xl mx-auto border border-zinc-800 bg-zinc-950/80 overflow-hidden" style={{ backgroundImage: SCAN_LINE_BG }}>
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-zinc-900/50">
        <span className="h-2 w-2 rounded-full bg-red-500/50" />
        <span className="h-2 w-2 rounded-full bg-amber-500/50" />
        <span className="h-2 w-2 rounded-full bg-emerald-500/50" />
        <span className="ml-2 text-[8px] font-[Space_Mono] text-zinc-600 tracking-wider uppercase">matcha-work // compliance-query</span>
      </div>
      <div className="p-5 min-h-[180px]">
        <p className="text-xs font-[Space_Mono] text-emerald-400 leading-relaxed">
          {query.slice(0, queryIdx)}
          {queryIdx < query.length && <span className="animate-pulse">▊</span>}
        </p>
        {queryIdx >= query.length && responseIdx > 0 && (
          <p className="text-xs font-[Space_Mono] text-zinc-400 leading-relaxed mt-4">
            {response.slice(0, responseIdx)}
            {responseIdx < response.length && <span className="animate-pulse text-amber-500">▊</span>}
          </p>
        )}
      </div>
    </div>
  )
}

/* ── Feature Section Data ─────────────────────────────────────── */
const SECTIONS = [
  {
    category: 'COMPLIANCE & LEGAL',
    accent: '#10b981',
    title: 'Compliance Engine',
    desc: 'Agentic jurisdiction research across federal, state, and local levels. Chain-of-reasoning compliance querying walks through regulatory logic step by step — citing sources, applying preemption rules, and surfacing gaps before returning a final answer.',
    graphic: JurisdictionCascade,
  },
  {
    category: 'COMPLIANCE & LEGAL',
    accent: '#f59e0b',
    title: 'Legislative Tracker',
    desc: 'Continuous monitoring of regulatory changes with pattern detection for coordinated legislative activity across jurisdictions. Real-time signal processing flags relevant changes before they become compliance gaps.',
    graphic: SignalMonitor,
  },
  {
    category: 'COMPLIANCE & LEGAL',
    accent: '#10b981',
    title: 'Risk Assessment',
    desc: '5-dimension live scoring with Monte Carlo simulation across 10,000 iterations, statistical anomaly detection on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW.',
    graphic: MonteCarloDistribution,
  },
  {
    category: 'INVESTIGATIONS & RISK',
    accent: '#f59e0b',
    title: 'ER Copilot',
    desc: 'Employment relations case management with agentic document analysis. Timeline construction and discrepancy detection. Encrypted PDF report generation with secure shared export links for external counsel.',
    graphic: TimelineConstructor,
  },
  {
    category: 'INVESTIGATIONS & RISK',
    accent: '#f59e0b',
    title: 'Incident Reports',
    desc: 'OSHA 300 and 300A auto-generation, anonymous reporting, and trend analytics with pattern detection across locations. Covers safety, behavioral, and compliance incidents.',
    graphic: PatternGrid,
  },
  {
    category: 'INVESTIGATIONS & RISK',
    accent: '#f59e0b',
    title: 'Pre-Termination Intel',
    desc: '9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before any separation decision. Generates a narrative memo suitable for counsel review.',
    graphic: RadarChart,
  },
]

export default function Landing() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div className="relative bg-zinc-900 text-zinc-100 overflow-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <div className="relative z-10">
        {/* Nav */}
        <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center px-6 pt-5">
          <div
            className="flex items-center justify-between w-full max-w-6xl px-6 py-3 rounded-full border border-zinc-700/30"
            style={{
              background: 'rgba(24, 24, 27, 0.6)',
              backdropFilter: 'blur(16px) saturate(1.4)',
              WebkitBackdropFilter: 'blur(16px) saturate(1.4)',
              boxShadow: '0 0 20px rgba(0,0,0,0.3), inset 0 0.5px 0 rgba(255,255,255,0.05)',
            }}
          >
            <div className="flex items-center gap-2.5">
              <img src="/logo.svg" alt="Matcha" className="h-5 w-5" />
              <span className="text-sm font-bold tracking-[0.25em] uppercase">
                Matcha
              </span>
            </div>
            <div className="hidden sm:flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              <span className="text-[10px] tracking-[0.2em] text-zinc-500 font-[Space_Mono] uppercase">
                Systems Online
              </span>
            </div>
            <div className="flex items-center gap-5">
              <span
                onClick={() => setIsPricingOpen(true)}
                className="hidden sm:inline text-[11px] tracking-[0.2em] text-zinc-400 font-[Space_Mono] uppercase hover:text-emerald-400 cursor-pointer transition-colors duration-300"
              >
                Pricing
              </span>
              <LinkButton
                to="/login"
                variant="ghost"
                size="sm"
                className="tracking-[0.2em] font-[Space_Mono] uppercase text-zinc-300 hover:text-emerald-400 border border-zinc-600/50 hover:border-emerald-500/40 rounded-full px-5 transition-all duration-300"
              >
                Login
              </LinkButton>
            </div>
          </div>
        </nav>

        {/* Hero */}
        <div className="relative pt-16">
          <AsciiHalftone />
        <section className="relative max-w-7xl mx-auto px-8 min-h-[90vh] flex items-center">
          {/* System tag */}
          <div className="absolute top-8 left-8 text-[11px] tracking-[0.12em] text-zinc-600 font-[Space_Mono] border border-zinc-700/40 px-3 py-1.5 rounded-sm">
            SYSTEM CORE // OFFLINE MODE
          </div>

          {/* Left content */}
          <div className="relative z-10 max-w-xl">
            <h1 className="font-[Orbitron] text-5xl sm:text-6xl lg:text-7xl font-black uppercase tracking-tight leading-[0.95]">
              Workforce
            </h1>
            <GlitchText
              text="Intelligence."
              cycleWords={["Compliance.", "Risk Assessment.", "Risk Management."]}
              className="block text-5xl sm:text-6xl lg:text-7xl italic font-light tracking-tight leading-[1.1] mt-1"
            />
            <p className="mt-8 text-lg sm:text-xl text-zinc-400 font-light">
              Increase your{' '}
              <span className="text-amber-500 font-normal">signal to noise ratio</span>.
            </p>
            <div className="mt-10">
              <LinkButton
                to="/login"
                variant="secondary"
                size="lg"
                className="tracking-[0.25em] font-[Space_Mono] uppercase border border-zinc-600 hover:border-zinc-400 px-10"
              >
                Initialize Account
              </LinkButton>
            </div>
          </div>

          {/* Particle Sphere */}
          <div className="absolute right-0 top-0 bottom-0 w-[60%] hidden lg:flex items-center justify-center">
            <Suspense
              fallback={
                <div className="text-zinc-600 font-[Space_Mono] text-[8px] uppercase tracking-[0.4em] animate-pulse">
                  Booting Neural Sphere...
                </div>
              }
            >
              <ParticleSphere className="w-full h-[70vh] opacity-80" />
            </Suspense>
          </div>

          {/* Scroll Down Chevron */}
          <button
            onClick={() => {
              document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
            }}
            className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 group cursor-pointer z-10"
            aria-label="Scroll down"
          >
            <span className="text-[9px] font-[Space_Mono] tracking-[0.3em] text-zinc-600 uppercase group-hover:text-zinc-400 transition-colors duration-300">
              Explore
            </span>
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              className="text-zinc-500 group-hover:text-emerald-400 transition-colors duration-300"
              style={{ animation: 'chevron-bounce 2s ease-in-out infinite' }}
            >
              <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </section>
        </div>

        {/* ── Global keyframes ──────────────────────────────────── */}
        <style>{`
          @keyframes ripple-expand {
            0% { transform: translate(-50%,-50%) scale(0.5); opacity: 0.3; }
            100% { transform: translate(-50%,-50%) scale(1.5); opacity: 0; }
          }
          @keyframes chevron-bounce {
            0%, 100% { transform: translateY(0); opacity: 0.6; }
            50% { transform: translateY(6px); opacity: 1; }
          }
        `}</style>

        {/* ── Feature Sections ─────────────────────────────────── */}
        {SECTIONS.map((section, idx) => {
          const reversed = idx % 2 === 1
          const Graphic = section.graphic
          return (
            <motion.section
              id={idx === 0 ? 'features' : undefined}
              key={section.title}
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.8 }}
              className="relative border-t border-zinc-700/40 py-20 sm:py-24 px-8 overflow-hidden"
            >
              {/* Dot grid background */}
              <div
                className="absolute inset-0 opacity-[0.04]"
                style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
              />

              <div className={`relative max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 lg:gap-20 items-center`}>
                {/* Text */}
                <motion.div
                  initial={{ opacity: 0, x: reversed ? 30 : -30 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
                  className={reversed ? 'lg:order-2' : ''}
                >
                  <div className="flex items-center gap-2 mb-5">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: section.accent }} />
                    <span className="text-xs tracking-[0.3em] uppercase text-zinc-500">
                      {section.category}
                    </span>
                  </div>
                  <h2 className="text-3xl sm:text-4xl font-bold uppercase tracking-wide text-zinc-100 mb-5">
                    {section.title}
                  </h2>
                  <p className="text-base text-zinc-400 leading-relaxed max-w-md">
                    {section.desc}
                  </p>
                </motion.div>

                {/* Graphic */}
                <motion.div
                  initial={{ opacity: 0, x: reversed ? -30 : 30 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.25 }}
                  className={`relative border border-zinc-800/60 bg-zinc-950/40 overflow-hidden ${reversed ? 'lg:order-1' : ''}`}
                >
                  <Graphic />
                </motion.div>
              </div>
            </motion.section>
          )
        })}

        {/* ── Matcha Work CTA ──────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="relative border-t border-zinc-700/40 py-24 px-8 overflow-hidden"
        >
          <div
            className="absolute inset-0 opacity-[0.04]"
            style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
          />
          <div className="relative max-w-7xl mx-auto">
            <div className="text-center mb-10">
              <span className="text-xs tracking-[0.3em] text-zinc-500 uppercase">
                Agentic Workspace
              </span>
              <h2 className="text-4xl sm:text-5xl font-light text-zinc-200 mt-4">
                Matcha Work
              </h2>
              <p className="text-zinc-500 text-sm sm:text-base mt-4 max-w-lg mx-auto leading-relaxed">
                Multi-threaded document workspace for compliance research, ER case analysis, regulatory reasoning chains, and cross-referencing organizational data.
              </p>
            </div>

            <TerminalTyping />

            <div className="text-center mt-10">
              <LinkButton
                to="/login"
                variant="secondary"
                size="lg"
                className="tracking-[0.25em] font-[Space_Mono] uppercase border border-zinc-600 hover:border-zinc-400 px-10"
              >
                Launch Workspace
              </LinkButton>
            </div>
          </div>
        </motion.section>

        {/* Footer */}
        <footer className="border-t border-zinc-700/50 py-6 px-8">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <p className="text-[10px] tracking-[0.15em] text-zinc-600 font-[Space_Mono] uppercase">
              &copy; {new Date().getFullYear()} Matcha Systems Inc.
              {import.meta.env.VITE_LANDING_BUILD_VERSION ? (
                <span className="ml-2 text-zinc-700">build {import.meta.env.VITE_LANDING_BUILD_VERSION}</span>
              ) : null}
            </p>
            <div className="flex gap-6">
              {['Terms', 'Privacy', 'Status'].map((link) => (
                <span
                  key={link}
                  className="text-[10px] tracking-[0.15em] text-zinc-600 font-[Space_Mono] uppercase hover:text-zinc-400 cursor-pointer transition-colors"
                >
                  {link}
                </span>
              ))}
            </div>
          </div>
        </footer>
      </div>
    </div>
  )
}
