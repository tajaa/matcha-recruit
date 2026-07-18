import { useEffect, useState } from 'react'

import { DarkFrame } from './DarkFrame'
import { WORKSPACE_THREADS } from './data'

export function WorkspaceMock() {
  const [activeThread, setActiveThread] = useState(0)
  const [revealedSteps, setRevealedSteps] = useState(-1)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const run = (threadIdx: number) => {
      if (cancelled) return
      setActiveThread(threadIdx)
      setRevealedSteps(-1)

      const thread = WORKSPACE_THREADS[threadIdx]
      thread.steps.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setRevealedSteps(idx)
        }, idx * 500 + 300))
      })

      // After all steps shown, switch to next thread
      const nextThreadMs = thread.steps.length * 500 + 300 + 2200
      timers.push(window.setTimeout(() => run((threadIdx + 1) % WORKSPACE_THREADS.length), nextThreadMs))
    }

    run(0)
    return () => { cancelled = true; clear() }
  }, [])

  const current = WORKSPACE_THREADS[activeThread]

  return (
    <DarkFrame label={`Document Workspace · ${WORKSPACE_THREADS.length} threads`}>
      <div className="flex h-full">
        <div className="w-[42%] border-r p-2 flex flex-col gap-1" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          {WORKSPACE_THREADS.map((t, i) => {
            const isActive = i === activeThread
            return (
              <div
                key={i}
                className="flex items-center gap-2 px-2 py-1.5 rounded transition-all duration-500"
                style={{
                  backgroundColor: isActive ? 'rgba(255,255,255,0.04)' : 'transparent',
                  border: `1px solid ${isActive ? 'rgba(215,186,125,0.3)' : 'transparent'}`,
                  boxShadow: isActive ? '0 0 12px rgba(215,186,125,0.08)' : 'none',
                }}
              >
                <span
                  className="w-1 h-1 rounded-full shrink-0 transition-all"
                  style={{
                    backgroundColor: t.color,
                    boxShadow: isActive ? `0 0 6px ${t.color}` : 'none',
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono truncate transition-colors duration-500" style={{ color: isActive ? '#e4ded2' : '#6a737d' }}>
                    {t.title}
                  </div>
                  <div className="text-[8px]" style={{ color: '#52525b' }}>
                    {t.lines} lines · {t.status}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <div className="flex-1 p-3 min-w-0 flex flex-col gap-1">
          <div className="text-[8px] uppercase tracking-wider font-mono mb-1" style={{ color: '#6a737d' }}>
            Reasoning chain · {current.title}
          </div>
          {current.steps.map((text, i) => {
            const revealed = revealedSteps >= i
            return (
              <div
                key={`${activeThread}-${i}`}
                className="flex gap-2 items-start transition-all duration-400"
                style={{
                  opacity: revealed ? 1 : 0.15,
                  transform: revealed ? 'translateX(0)' : 'translateX(-4px)',
                }}
              >
                <span
                  className="text-[9px] font-mono tabular-nums shrink-0 mt-[1px]"
                  style={{ color: revealed ? '#d7ba7d' : '#52525b' }}
                >
                  {i + 1}.
                </span>
                <span className="text-[9.5px] font-mono truncate" style={{ color: revealed ? '#d4d4d4' : '#52525b' }}>
                  {text}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </DarkFrame>
  )
}
