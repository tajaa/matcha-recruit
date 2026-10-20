import { AdminButton as Button, AdminInput as Input, AdminSelect as Select, AdminCard, AdminTable } from '../../../../components/admin/AdminUI'
import { AdminActionMenu } from '../../../../components/admin/AdminActionMenu'
import { AdminPagination } from '../../../../components/admin/AdminList'
import { useAdminPagination } from '../../../../components/admin/useAdminPagination'
import { useEffect, useMemo, useState } from 'react'
import { Copy } from 'lucide-react'
import { api } from '../../../../api/client'
import { useToast } from '../../../../components/ui'
import { formatDate } from '../../../../utils/dateFormat'
import type { CappePlanOption, CappeSignupGrant, CappeSignupGrantAccount } from '../../../../types/cappeAdmin'

const LINK_VALIDITY = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '', label: 'Until revoked' },
] as const

function grantState(grant: CappeSignupGrant): { label: string; className: string } {
  if (grant.revoked_at) return { label: 'Revoked', className: 'text-zinc-500' }
  if (grant.redeemed_count >= grant.max_redemptions) return { label: 'Used up', className: 'text-zinc-400' }
  if (grant.expires_at && new Date(grant.expires_at) <= new Date()) return { label: 'Expired', className: 'text-amber-300' }
  return { label: 'Active', className: 'text-emerald-300' }
}

// What happened to one person who signed up through a link.
function accountOutcome(account: CappeSignupGrantAccount): { text: string; className: string } {
  if (account.redeemed_at) return { text: `free from ${formatDate(account.redeemed_at)}`, className: 'text-zinc-500' }
  if (account.refused) return { text: `didn't get it: ${account.refused}`, className: 'text-amber-300' }
  if (account.email_verified_at) return { text: 'confirmed, but the plan failed to apply (give it by hand)', className: 'text-amber-300' }
  return { text: 'not confirmed yet', className: 'text-zinc-500' }
}

// Signup links: a new account made through one gets the plan free for its
// days, with no card. When the days run out the account drops to free and has
// to subscribe to keep the plan.
export default function CappeSignupGrants({ plans }: { plans: CappePlanOption[] | null }) {
  const { toast } = useToast()
  const paidPlans = useMemo(() => (plans ?? []).filter((plan) => plan.code !== 'free' && plan.status === 'active'), [plans])
  const [grants, setGrants] = useState<CappeSignupGrant[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [planCode, setPlanCode] = useState('')
  const [days, setDays] = useState('30')
  const [uses, setUses] = useState('1')
  const [email, setEmail] = useState('')
  const [linkValid, setLinkValid] = useState('30')
  const [note, setNote] = useState('')
  const [created, setCreated] = useState<CappeSignupGrant | null>(null)
  const pagination = useAdminPagination(grants)
  const chosenPlan = planCode || paidPlans[0]?.code || ''

  useEffect(() => {
    api.get<CappeSignupGrant[]>('/cappe/matcha-admin/signup-grants')
      .then(setGrants)
      .catch((error) => toast(error instanceof Error ? error.message : 'Could not load signup links', 'error'))
      .finally(() => setLoading(false))
  }, [toast])

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      toast('Link copied', 'success')
    } catch {
      toast('Copy failed — select the link and copy it by hand', 'error')
    }
  }

  async function createGrant(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const grant = await api.post<CappeSignupGrant>('/cappe/matcha-admin/signup-grants', {
        plan_code: chosenPlan,
        days: Number(days),
        max_redemptions: Number(uses),
        email: email.trim() || null,
        note: note.trim() || null,
        link_valid_days: linkValid ? Number(linkValid) : null,
      })
      setGrants((previous) => [grant, ...previous])
      setCreated(grant)
      setEmail('')
      setNote('')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not create the link', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function revoke(grant: CappeSignupGrant) {
    if (!window.confirm('Stop this link working? People who already confirmed keep their free days.')) return
    try {
      const updated = await api.post<CappeSignupGrant>(`/cappe/matcha-admin/signup-grants/${grant.id}/revoke`)
      setGrants((previous) => previous.map((item) => item.id === grant.id ? updated : item))
      if (created?.id === grant.id) setCreated(null)
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not revoke the link', 'error')
    }
  }

  if (loading || !plans) return <p className="text-sm text-zinc-500">Loading…</p>

  return (
    <div className="space-y-6">
      <AdminCard className="p-4">
        <p className="text-sm text-zinc-300">New signup link</p>
        <p className="mt-1 text-xs text-zinc-500">
          Whoever signs up through it gets the plan free for the days you set, counted from when they confirm their
          email. No card is asked for. After that the account drops to Free and has to subscribe to keep the plan.
        </p>
        <form onSubmit={createGrant} className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select label="Plan" value={chosenPlan} onChange={(event) => setPlanCode(event.target.value)} required
            options={paidPlans.map((plan) => ({ value: plan.code, label: plan.name }))} />
          <Input label="Free for (days)" type="number" min={1} max={366} required value={days} onChange={(event) => setDays(event.target.value)} />
          <Input label="How many signups" type="number" min={1} max={1000} required value={uses} onChange={(event) => setUses(event.target.value)} />
          <Input label="Only this email (optional)" type="email" placeholder="Anyone with the link" value={email} onChange={(event) => setEmail(event.target.value)} />
          <Select label="Link works for" value={linkValid} onChange={(event) => setLinkValid(event.target.value)} options={LINK_VALIDITY} />
          <Input label="Note (optional)" maxLength={500} placeholder="Who it's for" value={note} onChange={(event) => setNote(event.target.value)} />
          <div className="sm:col-span-3">
            <Button type="submit" disabled={busy || !chosenPlan}>{busy ? 'Creating…' : 'Create link'}</Button>
          </div>
        </form>
        {created && (
          <div className="mt-4 flex flex-wrap items-center gap-2 rounded border border-emerald-500/30 bg-emerald-500/[0.06] p-3">
            <p className="text-xs text-emerald-300">{created.plan_name} free for {created.days} days:</p>
            <code className="min-w-0 flex-1 break-all text-xs text-zinc-200">{created.signup_url}</code>
            <Button size="sm" variant="secondary" onClick={() => copy(created.signup_url)}><Copy className="mr-1 h-3.5 w-3.5" />Copy</Button>
          </div>
        )}
      </AdminCard>

      <div>
        {grants.length > 0 && <AdminPagination pagination={pagination} />}
        <AdminTable className="min-w-[900px]">
          <thead>
            <tr><th>Gives</th><th>Status</th><th className="text-right">Used</th><th>For</th><th>Signed up</th><th>Link expires</th><th className="text-right">Actions</th></tr>
          </thead>
          <tbody>
            {pagination.rows.map((grant) => {
              const state = grantState(grant)
              const more = grant.signup_count - grant.accounts.length
              return (
                <tr key={grant.id} className="align-top text-zinc-300">
                  <td>
                    <p className="text-zinc-100">{grant.plan_name} · {grant.days} days</p>
                    {grant.note && <p className="mt-0.5 text-xs text-zinc-500">{grant.note}</p>}
                    <p className="mt-0.5 text-[10px] text-zinc-600">{formatDate(grant.created_at)}{grant.created_by_email ? ` · ${grant.created_by_email}` : ''}</p>
                  </td>
                  <td className={state.className}>{state.label}</td>
                  <td className="text-right tabular-nums">{grant.redeemed_count} / {grant.max_redemptions}</td>
                  <td className="text-zinc-400">{grant.email ?? 'Anyone with the link'}</td>
                  <td>
                    {grant.accounts.length === 0 ? <span className="text-zinc-600">—</span> : grant.accounts.map((account) => {
                      const outcome = accountOutcome(account)
                      return (
                        <p key={account.id} className="text-xs">
                          <span className="text-zinc-300">{account.email}</span>{' '}
                          <span className={outcome.className}>· {outcome.text}</span>
                        </p>
                      )
                    })}
                    {more > 0 && <p className="text-[10px] text-zinc-600">and {more} earlier</p>}
                  </td>
                  <td className="text-zinc-400">{grant.expires_at ? formatDate(grant.expires_at) : 'Never'}</td>
                  <td className="text-right">
                    {state.label === 'Active' && (
                      <AdminActionMenu label={`Actions for ${grant.plan_name} link`} items={[
                        { label: 'Copy link', onSelect: () => copy(grant.signup_url) },
                        { label: 'Revoke', onSelect: () => revoke(grant), danger: true },
                      ]} />
                    )}
                  </td>
                </tr>
              )
            })}
            {grants.length === 0 && <tr><td colSpan={7} className="text-center text-zinc-500">No signup links yet.</td></tr>}
          </tbody>
        </AdminTable>
      </div>
    </div>
  )
}
