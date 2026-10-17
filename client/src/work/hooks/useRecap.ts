import { useEffect, useState } from 'react'
import { ApiError } from '../../api/client'
import { useMe } from '../../hooks/useMe'
import { getRecap } from '../api/matchaWork/recaps'
import type { RecapDetail } from '../types'

const TERMINAL = new Set(['ready', 'failed', 'skipped', 'expired', 'deleted'])

export function useRecap(id: string, revision: number) {
  const { me, isPersonal } = useMe()
  const owner = me?.user.id
  const [stored, setStored] = useState<{ owner: string; id: string; value: RecapDetail } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!owner || !isPersonal || !id) return
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const started = Date.now()
    let sequence = 0
    async function load() {
      clearTimeout(timer)
      if (document.hidden || !alive) return
      const request = ++sequence
      try {
        const value = await getRecap(id)
        if (!alive || request !== sequence) return
        setStored({ owner: owner!, id, value })
        setError(null)
        if (!TERMINAL.has(value.state)) timer = setTimeout(() => void load(), Date.now() - started > 60_000 ? 15_000 : 5000)
      } catch (caught) {
        if (!alive || request !== sequence) return
        if (caught instanceof ApiError && [401, 403, 404, 410].includes(caught.status)) {
          setStored(null)
          setError('This recap is unavailable. It may have been removed or access may have changed.')
        } else {
          setError('Connection interrupted. Retrying…')
          timer = setTimeout(() => void load(), 15_000)
        }
      }
    }
    const visibility = () => { ++sequence; clearTimeout(timer); if (!document.hidden) void load() }
    document.addEventListener('visibilitychange', visibility)
    void load()
    return () => { alive = false; clearTimeout(timer); document.removeEventListener('visibilitychange', visibility) }
  }, [id, revision, owner, isPersonal])
  return { recap: stored?.owner === owner && stored?.id === id && isPersonal ? stored.value : null, error }
}
