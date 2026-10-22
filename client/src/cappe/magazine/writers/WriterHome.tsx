import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cappeApi } from '../../api'
import type { CappeSite } from '../../types'
import { storiesPath, writerPaths } from './writerPaths'

/** `/cappe/writer` — a writer's home: their magazine's stories, or naming the
 *  magazine when there isn't one yet. */
export default function WriterHome() {
  const [to, setTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeSite[]>('/sites')
      .then((sites) => { if (live) setTo(sites[0] ? storiesPath(sites[0].id) : writerPaths.onboarding) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load your magazine') })
    return () => { live = false }
  }, [])

  if (error) return <p role="alert" className="p-8 text-sm text-red-400">{error}</p>
  if (!to) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
  return <Navigate replace to={to} />
}
