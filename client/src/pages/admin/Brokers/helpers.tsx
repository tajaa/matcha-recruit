import { Badge } from '../../../components/ui'

export const statusBadge = (status: string) => {
  if (status === 'active') return <Badge variant="success">Active</Badge>
  if (status === 'suspended') return <Badge variant="warning">Suspended</Badge>
  if (status === 'terminated') return <Badge variant="danger">Terminated</Badge>
  return <Badge variant="warning">{status}</Badge>
}
