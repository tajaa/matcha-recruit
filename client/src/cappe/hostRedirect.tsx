import { Navigate, useLocation } from 'react-router-dom'
import { cappePath } from './host'

/** Old gummfit.com/gummfit/... links land on the same page at the root. */
export default function GummfitPrefixRedirect() {
  const location = useLocation()
  return <Navigate to={`${cappePath(location.pathname, true)}${location.search}${location.hash}`} replace />
}
