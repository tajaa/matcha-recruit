import { Badge } from '../../../components/ui'

export const statusBadge = (status: string) => {
  if (status === 'active' || status === 'registered') return <Badge variant="success">{status}</Badge>
  if (status === 'invited' || status === 'pending') return <Badge variant="warning">{status}</Badge>
  if (status === 'expired') return <Badge variant="danger">Expired</Badge>
  return <Badge variant="warning">{status}</Badge>
}

export const onboardingStageBadge = (stage?: string) => {
  if (!stage) return <span className="text-zinc-600">—</span>
  const config: Record<string, { dot: string; label: string }> = {
    submitted: { dot: 'bg-zinc-700', label: 'Submitted' },
    under_review: { dot: 'bg-zinc-600', label: 'Under Review' },
    configuring: { dot: 'bg-zinc-500', label: 'Configuring' },
    live: { dot: 'bg-zinc-300', label: 'Live' },
  }
  const c = config[stage]
  if (!c) return <span className="text-zinc-600">—</span>
  return (
    <span className="flex items-center gap-1.5 text-xs text-zinc-300">
      <span className={`h-2 w-2 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  )
}

export function locationSummary(locations?: { city: string; state: string; type: string }[]) {
  if (!locations || locations.length === 0) return null
  if (locations.length === 1) {
    const l = locations[0]
    return `${l.city}${l.state ? ', ' + l.state : ''}`
  }
  return `${locations.length} locations`
}
