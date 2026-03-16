import { Badge } from '../ui'
import { statusLabel, statusVariant } from '../../types/employee'

export function EmployeeStatusBadge({ status }: { status: string | null }) {
  const key = status ?? 'active'
  return (
    <Badge variant={statusVariant[key] ?? 'neutral'}>
      {statusLabel[key] ?? key}
    </Badge>
  )
}
