import { useEffect, useState } from 'react'

import { DarkFrame } from './DarkFrame'
import { BAR_COUNT } from './data'

export function InterviewMock() {
  const [phase, setPhase] = useState(0)
  const [transcriptStep, setTranscriptStep] = useState(0) // 0: none, 1: interviewer, 2: candidate
  const [stats, setStats] = useState({ fluency: 0, technical: 0 })

  // Live waveform animation — continuous
  useEffect(() => {
    let raf = 0
    const start = performance.now()
    const tick = () => {
      const t = (performance.now() - start) / 1000
      setPhase(t)
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [])

  // Transcript + stats loop
  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const tickStat = (key: 'fluency' | 'technical', from: number, to: number, durationMs: number) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        setStats((prev) => ({ ...prev, [key]: Math.round(from + (to - from) * t) }))
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const run = () => {
      if (cancelled) return
      setTranscriptStep(0)
      setStats({ fluency: 0, technical: 0 })

      timers.push(window.setTimeout(() => { if (!cancelled) setTranscriptStep(1) }, 700))
      timers.push(window.setTimeout(() => { if (!cancelled) setTranscriptStep(2) }, 2400))
      timers.push(window.setTimeout(() => {
        if (cancelled) return
        tickStat('fluency', 0, 94, 900)
        tickStat('technical', 0, 88, 900)
      }, 3800))

      timers.push(window.setTimeout(run, 8000))
    }

    run()
    return () => { cancelled = true; clear() }
  }, [])

  return (
    <DarkFrame label="Voice Interview · Maya Chen">
      <div className="flex flex-col h-full p-4 gap-3 justify-center">
        {/* Live waveform */}
        <div className="flex items-center gap-[2px] h-16">
          {Array.from({ length: BAR_COUNT }, (_, i) => {
            // Continuous time-modulated amplitude per bar
            const base =
              Math.abs(Math.sin(i * 0.45 + phase * 2.2)) * 0.55 +
              Math.abs(Math.sin(i * 1.1 + phase * 3.1)) * 0.35 +
              0.08
            const h = Math.min(1, base)
            const isActive = i < (phase * 8) % BAR_COUNT + 8 && i > (phase * 8) % BAR_COUNT - 8
            const color = isActive ? '#86efac' : '#d7ba7d'
            return (
              <div
                key={i}
                className="flex-1 rounded-sm"
                style={{
                  height: `${h * 100}%`,
                  backgroundColor: color,
                  opacity: isActive ? 0.85 : 0.35,
                  boxShadow: isActive ? '0 0 6px rgba(134,239,172,0.45)' : 'none',
                  transition: 'height 120ms linear, opacity 200ms',
                }}
              />
            )
          })}
        </div>

        {/* Transcript lines */}
        <div className="space-y-1.5 font-mono text-[10.5px] min-h-[48px]">
          <div
            className="flex gap-2 transition-opacity duration-500"
            style={{ opacity: transcriptStep >= 1 ? 1 : 0 }}
          >
            <span style={{ color: '#6a737d' }} className="shrink-0">00:14</span>
            <span style={{ color: '#e4ded2' }}>
              "So when you scaled that Kubernetes cluster, what was the primary bottleneck?"
            </span>
          </div>
          <div
            className="flex gap-2 transition-opacity duration-500"
            style={{ opacity: transcriptStep >= 2 ? 1 : 0 }}
          >
            <span style={{ color: '#6a737d' }} className="shrink-0">00:21</span>
            <span style={{ color: '#9a8a70' }}>
              "The etcd write latency under high churn — we moved to a dedicated control plane..."
            </span>
          </div>
        </div>

        {/* Stats strip */}
        <div className="grid grid-cols-3 gap-1 pt-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          {[
            { label: 'CEFR', value: stats.fluency > 80 ? 'C1' : stats.fluency > 40 ? 'B2' : '—' },
            { label: 'Fluency', value: `${stats.fluency}%` },
            { label: 'Technical', value: `${stats.technical}%` },
          ].map((s) => (
            <div key={s.label} className="flex flex-col">
              <span className="text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>
                {s.label}
              </span>
              <span className="text-[14px] tabular-nums font-mono" style={{ color: '#e4ded2' }}>
                {s.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </DarkFrame>
  )
}
