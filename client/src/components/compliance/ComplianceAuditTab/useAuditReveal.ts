import { useEffect, useRef, useState } from 'react'
import type { RequirementComponent } from '../../../types/compliance'

export type RevealPhase = 'idle' | 'header' | 'root' | 'fanning' | 'done'
export type ClausePhase = 'pending' | 'weighing' | 'committed' | 'remediated'
export type ClauseState = { phase: ClausePhase; weighIdx: number }

const WEIGH_STEPS = 3
const TARGET_FAN_MS = 5600
const HEADER_MS = 700
const ROOT_MS = 600

// The landing animation's weighing strip cycles the same 3 meaningless
// strings for every clause. Here it explains why the clause landed where it
// did — the most honest thing on screen, since it shows a viewer that
// "unknown" clauses are blind because nothing in the product can prove them,
// not because the engine failed. `derivation_source` comes from the server's
// own Derivation registry (compliance_status.py) — no client-side copy of
// component_key -> table to drift out of sync with it.
export function weighingSteps(c: RequirementComponent): string[] {
  if (c.derivable) {
    return ['Matching statute', `Screening ${c.derivation_source ?? 'company records'}`, 'Scoring']
  }
  return ['Matching statute', 'No system record', 'Awaiting attestation']
}

type RunToken = { cancelled: boolean }

function sleep(ms: number, token: RunToken): Promise<void> {
  return new Promise((resolve) => {
    if (token.cancelled) return resolve()
    setTimeout(() => resolve(), ms)
  })
}

export function useAuditReveal(
  components: RequirementComponent[],
  opts: { active: boolean; runId: number },
) {
  const [phase, setPhase] = useState<RevealPhase>('idle')
  const [states, setStates] = useState<ClauseState[]>(() =>
    components.map(() => ({ phase: 'pending', weighIdx: 0 })))
  const [hud, setHud] = useState('')
  const skipRef = useRef(false)

  useEffect(() => {
    // A per-run token, not a component-lifetime ref: the previous run's async
    // loop may still be parked in an in-flight `sleep()` when this effect
    // re-fires (Replay, or close->reopen with a new runId). A shared ref reset
    // to `false` here would un-cancel that suspended run the instant it wakes,
    // and its own `finish()` would then slam every clause to 'remediated'
    // while THIS run is still fanning. Each run gets its own token; the
    // cleanup below only ever flips the token this effect created.
    const token: RunToken = { cancelled: false }
    skipRef.current = false

    if (!opts.active || components.length === 0) {
      setPhase('idle')
      return
    }

    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const n = components.length
    const per = Math.min(1150, Math.max(420, TARGET_FAN_MS / n))
    const WEIGH = (per * 0.56) / WEIGH_STEPS
    const COMMIT = per * 0.27
    const SPROUT = per * 0.17

    const finish = () => {
      if (token.cancelled) return  // superseded run: write nothing
      setStates(components.map(() => ({ phase: 'remediated', weighIdx: WEIGH_STEPS - 1 })))
      setPhase('done')
      const known = components.filter((c) => c.status !== 'unknown').length
      setHud(`Analysis complete · ${known}/${n} known`)
    }

    if (reduced) {
      finish()
      return
    }

    setStates(components.map(() => ({ phase: 'pending', weighIdx: 0 })))
    setPhase('idle')
    setHud('Loading statute...')

    async function run() {
      // Skip = jump to the resolved state now. Cancel (token.cancelled) =
      // this run was superseded; write nothing, ever — the new run owns the
      // screen. Conflating the two (as a single shared `bail()` used to) is
      // what let a stale run's `finish()` fire after a fresh one had started.
      const skipped = () => skipRef.current

      setPhase('header')
      setHud('Loading statute...')
      await sleep(HEADER_MS, token)
      if (token.cancelled) return
      if (skipped()) return finish()

      setPhase('root')
      setHud(`Decomposing audit into ${n} component checks...`)
      await sleep(ROOT_MS, token)
      if (token.cancelled) return
      if (skipped()) return finish()

      setPhase('fanning')
      for (let i = 0; i < n; i++) {
        if (token.cancelled) return
        if (skipped()) return finish()
        const c = components[i]
        setHud(`Checking: ${c.label}`)

        setStates((prev) => prev.map((s, idx) => (idx === i ? { phase: 'weighing', weighIdx: 0 } : s)))
        for (let w = 0; w < WEIGH_STEPS; w++) {
          if (token.cancelled) return
          if (skipped()) return finish()
          setStates((prev) => prev.map((s, idx) => (idx === i ? { ...s, weighIdx: w } : s)))
          await sleep(WEIGH, token)
        }

        if (token.cancelled) return
        if (skipped()) return finish()
        setStates((prev) => prev.map((s, idx) => (idx === i ? { ...s, phase: 'committed' } : s)))
        await sleep(COMMIT, token)

        if (token.cancelled) return
        if (skipped()) return finish()
        setStates((prev) => prev.map((s, idx) => (idx === i ? { ...s, phase: 'remediated' } : s)))
        await sleep(SPROUT, token)
      }

      if (token.cancelled) return
      finish()
    }

    run()
    return () => { token.cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.active, opts.runId, components.length])

  const skip = () => { skipRef.current = true }

  return { phase, states, hud, skip }
}
