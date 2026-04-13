import { useEffect, useState } from 'react'
import { AlertTriangle, Check, Loader2, Shield } from 'lucide-react'

type Status = 'flag' | 'fixing' | 'fixed'

type Row = {
  jurisdiction: string
  title: string
  severity: 'critical' | 'high' | 'medium'
}

const ROWS: Row[] = [
  { jurisdiction: 'CA', title: 'Meal Period Waivers missing for 12 employees', severity: 'critical' },
  { jurisdiction: 'NY', title: 'Paid Sick Leave accrual rate below statute', severity: 'critical' },
  { jurisdiction: 'FED', title: 'FLSA overtime threshold update not applied', severity: 'high' },
  { jurisdiction: 'WA', title: 'Predictive scheduling notice window expired', severity: 'high' },
  { jurisdiction: 'IL', title: 'BIPA biometric consent forms unsigned', severity: 'medium' },
  { jurisdiction: 'TX', title: 'Anti-retaliation posters out of date', severity: 'medium' },
]

const SEVERITY_COLOR: Record<Row['severity'], string> = {
  critical: '#ce9178',
  high: '#d7ba7d',
  medium: '#9a8a70',
}

const STEP_MS = 1600
const FIXING_MS = 700
const RESET_PAUSE_MS = 2400

export function ComplianceHeroAnimation() {
  const [statuses, setStatuses] = useState<Status[]>(() => ROWS.map(() => 'flag'))
  const [score, setScore] = useState(42)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []

    const clearTimers = () => {
      timers.forEach((t) => window.clearTimeout(t))
      timers = []
    }

    const run = () => {
      if (cancelled) return
      setStatuses(ROWS.map(() => 'flag'))
      setScore(42)

      ROWS.forEach((_, idx) => {
        const fixingAt = idx * STEP_MS + 400
        const fixedAt = fixingAt + FIXING_MS

        timers.push(
          window.setTimeout(() => {
            if (cancelled) return
            setStatuses((prev) => {
              const next = [...prev]
              next[idx] = 'fixing'
              return next
            })
          }, fixingAt),
        )

        timers.push(
          window.setTimeout(() => {
            if (cancelled) return
            setStatuses((prev) => {
              const next = [...prev]
              next[idx] = 'fixed'
              return next
            })
            setScore((prev) => Math.min(98, prev + Math.round((98 - 42) / ROWS.length)))
          }, fixedAt),
        )
      })

      const totalMs = ROWS.length * STEP_MS + FIXING_MS + RESET_PAUSE_MS
      timers.push(window.setTimeout(run, totalMs))
    }

    run()
    return () => {
      cancelled = true
      clearTimers()
    }
  }, [])

  const fixedCount = statuses.filter((s) => s === 'fixed').length

  return (
    <div
      className="relative w-full max-w-[640px] rounded-xl overflow-hidden"
      style={{
        backgroundColor: '#151412',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 40px 80px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04) inset',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4 border-b"
        style={{ borderColor: 'rgba(255,255,255,0.08)' }}
      >
        <div className="flex items-center gap-2.5">
          <Shield className="w-4 h-4" style={{ color: '#9a8a70' }} />
          <span
            className="text-[13px] font-medium tracking-wide"
            style={{ color: '#e4ded2', fontFamily: 'Inter, sans-serif' }}
          >
            Compliance Monitor
          </span>
          <span
            className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{ color: '#9a8a70', backgroundColor: 'rgba(154,138,112,0.12)' }}
          >
            Live
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px]" style={{ color: '#6a737d' }}>
            {fixedCount}/{ROWS.length} resolved
          </span>
          <div className="flex items-baseline gap-1">
            <span
              className="text-[22px] tabular-nums font-medium transition-colors duration-500"
              style={{
                color: score > 80 ? '#86efac' : score > 60 ? '#d7ba7d' : '#ce9178',
                fontFamily: 'Inter, sans-serif',
              }}
            >
              {score}
            </span>
            <span className="text-[11px]" style={{ color: '#6a737d' }}>/ 100</span>
          </div>
        </div>
      </div>

      {/* Rows */}
      <div className="divide-y" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
        {ROWS.map((row, idx) => {
          const status = statuses[idx]
          const isFixed = status === 'fixed'
          const isFixing = status === 'fixing'

          return (
            <div
              key={idx}
              className="flex items-center gap-3 px-5 py-3.5 transition-colors duration-500"
              style={{
                backgroundColor: isFixing
                  ? 'rgba(215,186,125,0.06)'
                  : isFixed
                  ? 'rgba(134,239,172,0.04)'
                  : 'transparent',
                borderColor: 'rgba(255,255,255,0.04)',
                borderBottomWidth: idx === ROWS.length - 1 ? 0 : 1,
                borderBottomStyle: 'solid',
              }}
            >
              {/* Jurisdiction tag */}
              <span
                className="text-[10px] font-medium tracking-wider px-2 py-0.5 rounded w-10 text-center shrink-0"
                style={{
                  color: isFixed ? '#86efac' : '#e4ded2',
                  backgroundColor: isFixed
                    ? 'rgba(134,239,172,0.08)'
                    : 'rgba(255,255,255,0.04)',
                  transition: 'color 500ms, background-color 500ms',
                }}
              >
                {row.jurisdiction}
              </span>

              {/* Title */}
              <span
                className="text-[12.5px] flex-1 truncate transition-colors duration-500"
                style={{
                  color: isFixed ? '#6a737d' : '#d4d4d4',
                  textDecoration: isFixed ? 'line-through' : 'none',
                  textDecorationColor: 'rgba(255,255,255,0.2)',
                  fontFamily: 'Inter, sans-serif',
                }}
              >
                {row.title}
              </span>

              {/* Status pill */}
              <div
                className="flex items-center gap-1.5 shrink-0 transition-all duration-500"
                style={{
                  color: isFixed ? '#86efac' : isFixing ? '#d7ba7d' : SEVERITY_COLOR[row.severity],
                }}
              >
                {isFixed ? (
                  <Check className="w-3.5 h-3.5" />
                ) : isFixing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <AlertTriangle className="w-3.5 h-3.5" />
                )}
                <span className="text-[10.5px] uppercase tracking-wider font-medium">
                  {isFixed ? 'Resolved' : isFixing ? 'Fixing' : 'Flagged'}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div
        className="px-5 py-3 border-t flex items-center justify-between"
        style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <span className="text-[10.5px] tracking-wide" style={{ color: '#6a737d' }}>
          Scanning 247 requirements across 6 jurisdictions
        </span>
        <span className="text-[10.5px] tabular-nums" style={{ color: '#9a8a70' }}>
          Updated just now
        </span>
      </div>
    </div>
  )
}
