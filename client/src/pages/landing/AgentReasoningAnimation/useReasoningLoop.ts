import { useEffect, useRef, useState } from 'react'
import { DECISIONS, INITIAL_STATES } from './data'
import type { DecisionState } from './types'

export function useReasoningLoop() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scenarioVisible, setScenarioVisible] = useState(false)
  const [rootVisible, setRootVisible] = useState(false)
  const [states, setStates] = useState<DecisionState[]>(INITIAL_STATES)
  const [synthesisVisible, setSynthesisVisible] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'auditing' | 'synthesized' | 'reset'>('idle')
  const [hudStatus, setHudStatus] = useState('Initializing CA jurisdiction graph...')
  const [gapCount, setGapCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    const visible = { current: true }
    const el = containerRef.current
    let obs: IntersectionObserver | null = null
    if (el) {
      obs = new IntersectionObserver(([e]) => { visible.current = e.isIntersecting }, { rootMargin: '200px' })
      obs.observe(el)
    }

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        const start = performance.now()
        const tick = () => {
          if (cancelled) return resolve()
          if (!visible.current) { setTimeout(tick, 200); return }
          const elapsed = performance.now() - start
          const remaining = ms - elapsed
          if (remaining <= 0) resolve()
          else setTimeout(tick, Math.min(remaining, 200))
        }
        tick()
      })

    const updateState = (idx: number, patch: Partial<DecisionState>) => {
      setStates(prev => prev.map((s, i) => i === idx ? { ...s, ...patch } : s))
    }

    async function loop() {
      while (!cancelled) {
        // RESET
        setScenarioVisible(false)
        setRootVisible(false)
        setStates(INITIAL_STATES)
        setSynthesisVisible(false)
        setGapCount(0)
        setPhase('idle')
        setHudStatus('Initializing CA jurisdiction graph...')
        await sleep(400)
        if (cancelled) return

        // SCENARIO CARD
        setPhase('auditing')
        setHudStatus('Loading SB 553 statute · Lab Code §6401.9...')
        setScenarioVisible(true)
        await sleep(1100)
        if (cancelled) return

        // ROOT NODE
        setHudStatus('Decomposing audit into 5 component checks...')
        setRootVisible(true)
        await sleep(900)
        if (cancelled) return

        // PER-DECISION FAN
        for (let i = 0; i < DECISIONS.length; i++) {
          if (cancelled) return
          const d = DECISIONS[i]
          setHudStatus(d.status)

          // Stage 1: weighing — cycle through candidate § citations
          updateState(i, { phase: 'weighing', weighIdx: 0 })
          for (let w = 0; w < d.weighing.length; w++) {
            if (cancelled) return
            updateState(i, { weighIdx: w })
            await sleep(280)
          }

          // Stage 2: commit
          updateState(i, { phase: 'committed' })
          if (d.result === 'GAP') setGapCount((g) => g + 1)
          await sleep(420)
          if (cancelled) return

          // Stage 3: remediation sprout
          updateState(i, { phase: 'remediated' })
          await sleep(280)
        }

        // SYNTHESIS
        if (cancelled) return
        setHudStatus('Drafting remediation plan · sequencing dependencies...')
        await sleep(700)
        setSynthesisVisible(true)
        setPhase('synthesized')
        setHudStatus('Analysis complete · 5/5 gaps found · draft plan ready for review')
        await sleep(6000)
        if (cancelled) return

        // FADE → loop
        setPhase('reset')
        await sleep(1000)
      }
    }

    loop()
    return () => {
      cancelled = true
      obs?.disconnect()
    }
  }, [])

  return {
    containerRef,
    scenarioVisible,
    rootVisible,
    states,
    synthesisVisible,
    phase,
    hudStatus,
    gapCount,
  }
}
