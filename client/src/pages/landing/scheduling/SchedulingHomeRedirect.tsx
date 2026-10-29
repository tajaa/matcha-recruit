import { Navigate, useLocation } from 'react-router-dom'

export default function SchedulingHomeRedirect() {
  const { search, hash } = useLocation()
  return <Navigate to={{ pathname: '/scheduling', search, hash }} replace />
}
