import { Link } from 'react-router-dom'
import { useWorkBase, useWorkSurface } from '../../routes/WorkSurfaceContext'
import { useRecapPreferences } from '../../hooks/useRecapPreferences'

export default function RecapLink({ recapId, sourceId }: { recapId?: string; sourceId?: string }) {
  const base = useWorkBase()
  const surface = useWorkSurface()
  const preferences = useRecapPreferences()
  if (surface !== 'espresso' || (!recapId && !preferences?.available)) return null
  const href = recapId ? `${base}/recaps/${encodeURIComponent(recapId)}` : `${base}/recaps?source_id=${encodeURIComponent(sourceId ?? '')}`
  return <Link to={href} className="inline-flex rounded-md border border-w-line px-2 py-1 text-xs text-w-dim hover:bg-w-surface2">Task recap</Link>
}
