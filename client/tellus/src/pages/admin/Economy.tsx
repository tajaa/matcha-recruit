import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, ErrorText, Input } from '../../components/ui'
import type { AdminBadge, AdminEarningRule, AdminListing } from '../../api/types'

const LABEL = 'font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-tu-faint'

function toErrorMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}

function EarningRules() {
  const [rules, setRules] = useState<AdminEarningRule[]>([])
  const [drafts, setDrafts] = useState<Record<string, Partial<AdminEarningRule>>>({})
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    tellusApi.get<AdminEarningRule[]>('/admin/earning-rules')
      .then(setRules)
      .catch((e) => setError(toErrorMessage(e, 'Failed to load earning rules')))
  }, [])

  function draftFor(r: AdminEarningRule): AdminEarningRule {
    return { ...r, ...drafts[r.event_key] }
  }

  function isDirty(r: AdminEarningRule): boolean {
    const d = drafts[r.event_key]
    if (!d) return false
    return (
      (d.points !== undefined && d.points !== r.points)
      || (d.daily_cap !== undefined && d.daily_cap !== r.daily_cap)
      || (d.cooldown_seconds !== undefined && d.cooldown_seconds !== r.cooldown_seconds)
      || (d.is_active !== undefined && d.is_active !== r.is_active)
    )
  }

  async function save(r: AdminEarningRule) {
    const d = drafts[r.event_key]
    if (!d) return
    setBusyKey(r.event_key)
    setError('')
    try {
      const updated = await tellusApi.patch<AdminEarningRule>(`/admin/earning-rules/${r.event_key}`, d)
      setRules((rs) => rs.map((x) => (x.event_key === r.event_key ? updated : x)))
      setDrafts((ds) => { const n = { ...ds }; delete n[r.event_key]; return n })
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to save earning rule'))
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <Card>
      <div className={`mb-3 ${LABEL}`}>Earning rules</div>
      <ErrorText>{error}</ErrorText>
      <div className="space-y-2">
        {rules.map((r) => {
          const d = draftFor(r)
          return (
            <div key={r.event_key} className="flex flex-wrap items-end gap-2 border-b border-tu-border/50 pb-2 last:border-b-0">
              <span className="w-40 font-mono text-xs text-tu-faint">{r.event_key}</span>
              <div className="w-24">
                <Input
                  label="Points" type="number" value={d.points}
                  onChange={(e) => setDrafts((ds) => ({ ...ds, [r.event_key]: { ...ds[r.event_key], points: Number(e.target.value) } }))}
                />
              </div>
              <div className="w-24">
                <Input
                  label="Daily cap" type="number" value={d.daily_cap ?? ''}
                  onChange={(e) => setDrafts((ds) => ({ ...ds, [r.event_key]: { ...ds[r.event_key], daily_cap: e.target.value === '' ? null : Number(e.target.value) } }))}
                />
              </div>
              <div className="w-28">
                <Input
                  label="Cooldown (s)" type="number" value={d.cooldown_seconds ?? ''}
                  onChange={(e) => setDrafts((ds) => ({ ...ds, [r.event_key]: { ...ds[r.event_key], cooldown_seconds: e.target.value === '' ? null : Number(e.target.value) } }))}
                />
              </div>
              <label className="flex items-center gap-1.5 pb-2 text-xs text-tu-dim">
                <input
                  type="checkbox" checked={d.is_active}
                  onChange={(e) => setDrafts((ds) => ({ ...ds, [r.event_key]: { ...ds[r.event_key], is_active: e.target.checked } }))}
                />
                Active
              </label>
              <Button size="sm" variant="soft" disabled={!isDirty(r)} loading={busyKey === r.event_key} onClick={() => void save(r)}>Save</Button>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function Badges() {
  const [badges, setBadges] = useState<AdminBadge[]>([])
  const [drafts, setDrafts] = useState<Record<string, { name?: string; threshold?: number }>>({})
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    tellusApi.get<AdminBadge[]>('/admin/badges')
      .then(setBadges)
      .catch((e) => setError(toErrorMessage(e, 'Failed to load badges')))
  }, [])

  async function save(b: AdminBadge) {
    const d = drafts[b.key]
    if (!d) return
    setBusyKey(b.key)
    setError('')
    try {
      const updated = await tellusApi.patch<AdminBadge>(`/admin/badges/${b.key}`, d)
      setBadges((bs) => bs.map((x) => (x.key === b.key ? updated : x)))
      setDrafts((ds) => { const n = { ...ds }; delete n[b.key]; return n })
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to save badge'))
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <Card>
      <div className={`mb-3 ${LABEL}`}>Badges</div>
      <ErrorText>{error}</ErrorText>
      <div className="space-y-2">
        {badges.map((b) => {
          const d = drafts[b.key] ?? {}
          const dirty = d.name !== undefined || d.threshold !== undefined
          return (
            <div key={b.key} className="flex flex-wrap items-end gap-2 border-b border-tu-border/50 pb-2 last:border-b-0">
              <div className="w-40">
                <Input
                  label="Name" value={d.name ?? b.name}
                  onChange={(e) => setDrafts((ds) => ({ ...ds, [b.key]: { ...ds[b.key], name: e.target.value } }))}
                />
              </div>
              <div className="w-24">
                <Input
                  label="Threshold" type="number" min={1} value={d.threshold ?? b.criteria.threshold ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value
                    setDrafts((ds) => ({
                      ...ds,
                      [b.key]: { ...ds[b.key], threshold: raw === '' ? undefined : Number(raw) },
                    }))
                  }}
                />
              </div>
              <span className="pb-2 text-xs text-tu-faint">{b.award_count} awarded</span>
              <Button size="sm" variant="soft" disabled={!dirty} loading={busyKey === b.key} onClick={() => void save(b)}>Save</Button>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function Listings() {
  const [listings, setListings] = useState<AdminListing[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function load() {
    try {
      const res = await tellusApi.get<{ items: AdminListing[] }>('/admin/listings')
      setListings(res.items)
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to load listings'))
    }
  }

  useEffect(() => { void load() }, [])

  async function toggle(l: AdminListing) {
    if (l.is_active && !window.confirm(`Deactivate "${l.title}"?`)) return
    setBusyId(l.id)
    setError('')
    try {
      await tellusApi.patch(`/admin/listings/${l.id}`, { is_active: !l.is_active })
      await load()
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to update listing'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Card>
      <div className={`mb-3 ${LABEL}`}>Marketplace listings</div>
      <ErrorText>{error}</ErrorText>
      <div className="space-y-1">
        {listings.map((l) => (
          <div key={l.id} className="flex items-center justify-between border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
            <div className="min-w-0 flex-1">
              <span className="text-tu-text">{l.title}</span>{' '}
              <span className="text-tu-faint">{l.brand_name ?? 'Platform'} · {l.points_cost} pts · {l.quantity_claimed}/{l.quantity_total ?? '∞'}</span>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Chip tone={l.is_active ? 'positive' : 'negative'}>{l.is_active ? 'active' : 'inactive'}</Chip>
              <Button size="sm" variant="soft" loading={busyId === l.id} onClick={() => void toggle(l)}>
                {l.is_active ? 'Deactivate' : 'Activate'}
              </Button>
            </div>
          </div>
        ))}
        {listings.length === 0 && <p className="text-sm text-tu-faint">No listings yet.</p>}
      </div>
    </Card>
  )
}

export default function AdminEconomy() {
  return (
    <div className="space-y-4 pb-8">
      <div className="flex items-center gap-2 px-1">
        <Sparkles className="h-4 w-4 text-tu-accent" />
        <h1 className="text-sm font-semibold text-tu-text">Economy</h1>
      </div>
      <EarningRules />
      <Badges />
      <Listings />
    </div>
  )
}
