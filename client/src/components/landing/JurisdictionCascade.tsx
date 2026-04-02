import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

/* ── Jurisdiction Cascade (Compliance Engine) ─────────────────── */
export function JurisdictionCascade() {
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
            className="text-[9px] uppercase mb-2 transition-all duration-700"
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
                className="px-2.5 py-1 border text-[9px] transition-all duration-500"
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
        <span className="text-[8px] text-emerald-500/60 uppercase">Live</span>
      </div>
    </div>
  )
}