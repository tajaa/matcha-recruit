import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck, UserPlus } from 'lucide-react'
import { useToast } from '../../components/ui'
import {
  getMyOpsAccess,
  listOpsPermissions,
  revokeOpsPermission,
  upsertOpsPermission,
  type OpsAccessLevel,
  type OpsPermissionGrant,
  type OpsSelfAccess,
} from '../../api/ops/permissions'

const GRANT_LEVELS: OpsAccessLevel[] = ['member', 'reviewer', 'operator', 'admin']

export default function OpsAccess() {
  const { toast } = useToast()
  const [access, setAccess] = useState<OpsSelfAccess | null>(null)
  const [grants, setGrants] = useState<OpsPermissionGrant[]>([])
  const [userId, setUserId] = useState('')
  const [level, setLevel] = useState<OpsAccessLevel>('member')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const current = await getMyOpsAccess()
      setAccess(current)
      if (current.can_manage) setGrants(await listOpsPermissions())
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not load Ops access', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function saveGrant(targetUserId: string, targetLevel: OpsAccessLevel) {
    const trimmed = targetUserId.trim()
    if (!trimmed) return
    setSaving(trimmed)
    try {
      const grant = await upsertOpsPermission(trimmed, targetLevel)
      setGrants((current) => {
        const without = current.filter((item) => item.user_id !== grant.user_id)
        return [...without, grant].sort((a, b) => a.name.localeCompare(b.name))
      })
      setUserId('')
      toast('Ops permission saved', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not save Ops permission', 'error')
    } finally {
      setSaving(null)
    }
  }

  async function removeGrant(grant: OpsPermissionGrant) {
    setSaving(grant.user_id)
    try {
      await revokeOpsPermission(grant.user_id)
      setGrants((current) => current.filter((item) => item.user_id !== grant.user_id))
      toast('Ops permission revoked', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not revoke Ops permission', 'error')
    } finally {
      setSaving(null)
    }
  }

  if (loading) {
    return <div className="flex min-h-[50vh] items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-w-dim" /></div>
  }

  if (!access) {
    return <div className="p-6 text-sm text-w-dim">Ops access is unavailable for this account.</div>
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <ShieldCheck className="text-w-accent" size={22} />
        <div>
          <h1 className="text-xl font-semibold text-w-text">Ops access</h1>
          <p className="mt-1 text-sm text-w-dim">Company-scoped permissions for Events and operational automation.</p>
        </div>
      </div>

      <section className="rounded-xl border border-w-line bg-w-surface p-5">
        <p className="text-xs uppercase tracking-wider text-w-dim">Your access</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-w-accent/15 px-3 py-1 text-sm font-medium capitalize text-w-accent">{access.level}</span>
          <span className="text-xs text-w-dim">Source: {access.source.replaceAll('_', ' ')}</span>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {access.capabilities.map((capability) => <span key={capability} className="rounded-md border border-w-line px-2 py-1 text-xs text-w-dim">{capability}</span>)}
        </div>
      </section>

      {access.can_manage && (
        <section className="rounded-xl border border-w-line bg-w-surface p-5">
          <div>
            <h2 className="text-sm font-medium text-w-text">Permission grants</h2>
            <p className="mt-1 text-xs text-w-dim">Grant Ops access by user UUID. Every change is audited.</p>
          </div>

          <form
            className="mt-4 flex flex-col gap-2 sm:flex-row"
            onSubmit={(event) => { event.preventDefault(); void saveGrant(userId, level) }}
          >
            <input
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="User UUID"
              className="min-w-0 flex-1 rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent"
            />
            <select value={level} onChange={(event) => setLevel(event.target.value as OpsAccessLevel)} className="rounded-md border border-w-line bg-w-bg px-3 py-2 text-sm text-w-text">
              {GRANT_LEVELS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <button type="submit" disabled={!userId.trim() || saving !== null} className="inline-flex items-center justify-center gap-2 rounded-md bg-w-accent px-3 py-2 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-50">
              <UserPlus size={15} /> Grant
            </button>
          </form>

          <div className="mt-5 divide-y divide-w-line">
            {grants.map((grant) => (
              <div key={grant.user_id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-w-text">{grant.name}</p>
                  <p className="truncate text-xs text-w-dim">{grant.email} · {grant.user_id}</p>
                </div>
                <select
                  value={grant.level}
                  disabled={saving === grant.user_id}
                  onChange={(event) => void saveGrant(grant.user_id, event.target.value as OpsAccessLevel)}
                  className="rounded-md border border-w-line bg-w-bg px-2 py-1.5 text-xs capitalize text-w-text"
                >
                  {GRANT_LEVELS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <button type="button" disabled={saving === grant.user_id} onClick={() => void removeGrant(grant)} className="text-xs text-red-300 hover:text-red-200 disabled:opacity-50">Revoke</button>
              </div>
            ))}
            {grants.length === 0 && <p className="py-5 text-sm text-w-dim">No explicit grants. Company defaults still apply.</p>}
          </div>
        </section>
      )}
    </div>
  )
}
