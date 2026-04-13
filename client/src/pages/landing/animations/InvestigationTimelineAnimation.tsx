import { useEffect, useState } from 'react'
import { FileText, Mail, MessageSquare, Search, Gavel, Check, AlertOctagon } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// Horizontal ER investigation timeline — mirrors TimelineConstructor's visual vocabulary.
// Shows document cards above nodes + pattern-match alert at the bottom.

type Step = {
  label: string
  icon: LucideIcon
  doc: string
}

const STEPS: Step[] = [
  { label: 'Intake',        icon: Mail,          doc: 'Complaint' },
  { label: 'Interviews',    icon: MessageSquare, doc: 'Witness·3' },
  { label: 'Document scan', icon: FileText,      doc: 'Exhibits·47' },
  { label: 'Analysis',      icon: Search,        doc: 'Timeline·MD' },
  { label: 'Resolution',    icon: Gavel,         doc: 'Memo·PDF' },
]

const STEP_MS = 1050
const ALERT_SHOW_AT_STEP = 3
const RESET_PAUSE_MS = 2600

export function InvestigationTimelineAnimation() {
  const [current, setCurrent] = useState(-1) // -1 = nothing, N = step N active, STEPS.length = all done
  const [elapsed, setElapsed] = useState(0)
  const [alertVisible, setAlertVisible] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const tickDays = (from: number, to: number, durationMs: number) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        setElapsed(Math.round(from + (to - from) * t))
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const run = () => {
      if (cancelled) return
      setCurrent(-1); setElapsed(0); setAlertVisible(false)

      STEPS.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setCurrent(idx)
        }, idx * STEP_MS + 500))
      })

      // Pattern-match alert pops when we hit the Analysis step
      timers.push(window.setTimeout(() => {
        if (cancelled) return
        setAlertVisible(true)
      }, ALERT_SHOW_AT_STEP * STEP_MS + 700))

      // Elapsed day counter ramps across the whole scan
      timers.push(window.setTimeout(() => tickDays(0, 12, STEPS.length * STEP_MS + 600), 400))

      timers.push(window.setTimeout(() => {
        if (cancelled) return
        setCurrent(STEPS.length)
      }, STEPS.length * STEP_MS + 600))

      const totalMs = STEPS.length * STEP_MS + 600 + RESET_PAUSE_MS
      timers.push(window.setTimeout(run, totalMs))
    }

    run()
    return () => { cancelled = true; clear() }
  }, [])

  const getStatus = (idx: number) => {
    if (current === -1) return 'pending' as const
    if (current >= STEPS.length) return 'done' as const
    if (idx < current) return 'done' as const
    if (idx === current) return 'active' as const
    return 'pending' as const
  }

  const complete = current >= STEPS.length
  const progressPct = current < 0 ? 0 : Math.min(100, ((current + 0.5) / STEPS.length) * 100)

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
          <Gavel className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            ER Copilot Engine
          </span>
          <span className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: complete ? '#86efac' : '#d7ba7d', border: `1px solid ${complete ? 'rgba(134,239,172,0.4)' : 'rgba(215,186,125,0.4)'}` }}>
            {complete ? 'Resolved' : 'Active'}
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>Case</span>
          <span className="tabular-nums" style={{ color: '#d7ba7d' }}>ER-0142</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>{elapsed}d elapsed</span>
        </div>
      </div>

      {/* Body: horizontal timeline */}
      <div className="relative flex-1 flex flex-col justify-center px-6 py-4 min-h-0">
        {/* Base line */}
        <div className="relative w-full">
          {/* Background line */}
          <div
            className="absolute top-1/2 left-0 right-0 h-[1px] -translate-y-1/2"
            style={{ backgroundColor: 'rgba(255,255,255,0.08)' }}
          />
          {/* Progress line */}
          <div
            className="absolute top-1/2 left-0 h-[2px] -translate-y-1/2 transition-all duration-700"
            style={{
              width: `${progressPct}%`,
              backgroundColor: '#d7ba7d',
              boxShadow: '0 0 8px rgba(215,186,125,0.6)',
            }}
          />

          {/* Step nodes */}
          <div className="relative flex justify-between items-center">
            {STEPS.map((step, idx) => {
              const status = getStatus(idx)
              const active = status === 'active'
              const done = status === 'done'
              const StepIcon = step.icon

              return (
                <div key={idx} className="flex flex-col items-center relative" style={{ width: `${100 / STEPS.length}%` }}>
                  {/* Document card above */}
                  <div
                    className="absolute -top-[46px] left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 transition-all duration-500"
                    style={{
                      opacity: status !== 'pending' ? 1 : 0.25,
                      transform: `translate(-50%, ${status !== 'pending' ? '0' : '4px'})`,
                    }}
                  >
                    <div
                      className="flex items-center justify-center w-8 h-10 rounded-sm border"
                      style={{
                        borderColor: done ? 'rgba(134,239,172,0.5)' : active ? 'rgba(215,186,125,0.6)' : 'rgba(255,255,255,0.1)',
                        backgroundColor: done ? 'rgba(134,239,172,0.08)' : active ? 'rgba(215,186,125,0.1)' : 'rgba(255,255,255,0.02)',
                        boxShadow: active ? '0 0 12px rgba(215,186,125,0.3)' : 'none',
                      }}
                    >
                      <StepIcon
                        className="w-3.5 h-3.5"
                        style={{ color: done ? '#86efac' : active ? '#d7ba7d' : '#52525b' }}
                      />
                    </div>
                    <span className="text-[7px] font-mono uppercase tracking-wide" style={{ color: done ? '#86efac' : active ? '#d7ba7d' : '#52525b' }}>
                      {step.doc}
                    </span>
                  </div>

                  {/* Node dot */}
                  <div
                    className="relative w-3 h-3 rounded-full flex items-center justify-center transition-all duration-300"
                    style={{
                      backgroundColor: done ? '#86efac' : active ? '#d7ba7d' : '#2a2826',
                      border: `1px solid ${done ? '#86efac' : active ? '#d7ba7d' : '#3f3f46'}`,
                      boxShadow: active ? '0 0 0 3px rgba(215,186,125,0.15), 0 0 10px rgba(215,186,125,0.5)' : 'none',
                    }}
                  >
                    {done && <Check className="w-2 h-2" style={{ color: '#0e0d0b' }} strokeWidth={3.5} />}
                    {active && (
                      <div
                        className="absolute inset-0 rounded-full animate-ping"
                        style={{ backgroundColor: '#d7ba7d', opacity: 0.4 }}
                      />
                    )}
                  </div>

                  {/* Label below */}
                  <div className="absolute top-[22px] left-1/2 -translate-x-1/2 text-[8.5px] font-mono uppercase tracking-wide whitespace-nowrap transition-colors duration-300" style={{ color: done || active ? '#e4ded2' : '#52525b' }}>
                    {step.label}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Pattern-match alert popup */}
        <div
          className="absolute left-4 right-4 bottom-3 rounded-sm border px-3 py-2 flex items-center gap-2 transition-all duration-500"
          style={{
            borderColor: 'rgba(206,145,120,0.45)',
            backgroundColor: 'rgba(206,145,120,0.08)',
            boxShadow: '0 0 20px rgba(206,145,120,0.15)',
            opacity: alertVisible ? 1 : 0,
            transform: alertVisible ? 'translateY(0)' : 'translateY(6px)',
          }}
        >
          <AlertOctagon className="w-3.5 h-3.5 shrink-0" style={{ color: '#ce9178' }} />
          <div className="flex-1 min-w-0">
            <div className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#ce9178' }}>
              Pattern match detected
            </div>
            <div className="text-[9.5px] font-mono truncate" style={{ color: '#e4ded2' }}>
              Similar to ER-0089 (94% sim) · ER-0117 (87% sim)
            </div>
          </div>
          <span className="text-[8px] font-mono uppercase tracking-wider shrink-0 px-1.5 py-[1px] rounded" style={{ color: '#ce9178', border: '1px solid rgba(206,145,120,0.45)' }}>
            Cluster
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[8.5px]" style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        <div className="flex items-center gap-3">
          <span style={{ color: '#6a737d' }}>3 witnesses</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>47 exhibits</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>Chain of custody ✓</span>
        </div>
        <span style={{ color: '#9a8a70' }}>
          {complete ? 'Memo ready' : `Step ${Math.max(0, current + 1)}/${STEPS.length}`}
        </span>
      </div>
    </div>
  )
}
