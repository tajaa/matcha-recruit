import { Navigate, useSearchParams } from 'react-router-dom'
import { recapsPath } from '../components/recaps/paths'
import { useWorkBase } from '../routes/WorkSurfaceContext'

/** `/recaps` moved into Tasks; old links keep working. */
export default function Recaps() {
  const base = useWorkBase()
  const [query] = useSearchParams()
  return <Navigate replace to={recapsPath(base, { source: query.get('source_id') })} />
}
