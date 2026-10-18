import { Navigate, useParams } from 'react-router-dom'
import { recapsPath } from '../components/recaps/paths'
import { useWorkBase } from '../routes/WorkSurfaceContext'

/** `/recaps/:id` (the recap email's link) opens the recap in Tasks. */
export default function Recap() {
  const { recapId } = useParams()
  const base = useWorkBase()
  return <Navigate replace to={recapsPath(base, { recap: recapId })} />
}
