import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../../api/client'
import { getAgentTaskDraft, startAgentTaskDraft } from '../../../api/matchaWork'
import type { MWTaskDraft } from '../../../types'

export function useAgentTaskDraft(projectId: string, onDraft: (draft: MWTaskDraft) => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const generation = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onDraftRef = useRef(onDraft)
  useEffect(() => { onDraftRef.current = onDraft }, [onDraft])

  useEffect(() => () => {
    generation.current += 1
    if (timer.current) clearTimeout(timer.current)
  }, [projectId])

  const start = useCallback(async (prompt: string) => {
    const trimmed = prompt.trim()
    if (!trimmed || trimmed.length > 12000) {
      setError('Describe the task in 12,000 characters or less.')
      return
    }
    generation.current += 1
    const current = generation.current
    if (timer.current) clearTimeout(timer.current)
    setBusy(true)
    setStatus('queued')
    setError(null)
    try {
      const run = await startAgentTaskDraft(projectId, trimmed, crypto.randomUUID())
      const poll = async () => {
        try {
          const result = await getAgentTaskDraft(projectId, run.run_id)
          if (current !== generation.current) return
          setStatus(result.status)
          if (result.status === 'completed') {
            setBusy(false)
            if (result.draft) onDraftRef.current(result.draft)
            else setError('The run completed without a ticket draft.')
          } else if (result.status === 'failed' || result.status === 'cancelled') {
            setBusy(false)
            setError(result.error ?? 'Could not draft a ticket from this repository.')
          } else {
            timer.current = setTimeout(poll, 2000)
          }
        } catch (cause) {
          if (current !== generation.current) return
          setBusy(false)
          setError(cause instanceof Error ? cause.message : 'Could not check the draft run.')
        }
      }
      if (current === generation.current) await poll()
    } catch (cause) {
      if (current !== generation.current) return
      setBusy(false)
      setError(cause instanceof ApiError && cause.status === 412
        ? 'Connect a GitHub repository to this project first.'
        : cause instanceof Error ? cause.message : 'Could not start the draft run.')
    }
  }, [projectId])

  return { busy, error, status, start }
}
