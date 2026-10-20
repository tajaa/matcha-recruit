/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminStat as Stat, AdminButton as Button, AdminInput as Input, AdminSelect as Select, AdminTextarea as Textarea, AdminTable } from '../../../../components/admin/AdminUI'
import { AdminTabs as PillTabs, AdminTab, AdminTabBar } from '../../../../components/admin/AdminTabs'
import { AdminPageHeader } from '../../../../components/admin/AdminPageHeader'
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import { api } from '../../../../api/client'
import { cappeSiteHost } from '../../../../cappe/host'
import { Modal, useToast } from '../../../../components/ui'
import CappeCreators from './CappeCreators'
import CappeSignupGrants from './CappeSignupGrants'
import type { CappePlanOption } from '../../../../types/cappeAdmin'

type CappeSite = {
  id: string
  name: string
  slug: string
  subdomain: string | null
  custom_domain: string | null
  status: string
  page_count: number
  order_count: number
  revenue_cents: number
  created_at: string | null
  published_at: string | null
}

type CappeAccount = {
  id: string
  email: string
  name: string | null
  plan: string
  status: string
  account_type: string
  email_verified_at: string | null
  created_at: string | null
  // The live subscription: 'stripe' pays, 'comp' was given by an admin or a
  // signup link and ends at comped_until (null = no end date).
  subscription_source: 'stripe' | 'comp' | null
  subscription_status: string | null
  comped_until: string | null
  campaign_count: number
  offers_sent: number
  active_collabs: number
  collab_spend_cents: number
  site_count: number
  published_count: number
  order_count: number
  revenue_cents: number
  sites: CappeSite[]
}

type CappeTotals = {
  account_count: number
  plan_counts: Record<string, number>
  site_count: number
  published_count: number
  order_count: number
  revenue_cents: number
}

type CappeListResponse = { accounts: CappeAccount[]; totals: CappeTotals }
type PlanFilter = 'all' | 'free' | 'creator' | 'business' | 'hosting' | 'pro'
type View = 'websites' | 'brands' | 'creators' | 'grants'

const PLAN_LABEL: Record<Exclude<PlanFilter, 'all'>, string> = {
  free: 'Free', creator: 'Creator', business: 'Business', hosting: 'Hosting', pro: 'Pro',
}

const PLAN_BADGE_CLASS: Record<string, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  hosting: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
  pro: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  business: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
}

function PlanBadge({ plan }: { plan: string }) {
  return <span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] ${PLAN_BADGE_CLASS[plan] ?? PLAN_BADGE_CLASS.free}`}>{PLAN_LABEL[plan as Exclude<PlanFilter, 'all'>] ?? plan}</span>
}

// The plan, plus how the account holds it when it isn't free: paid through
// Stripe, or given free (until a date, or with no end).
function PlanCell({ account }: { account: CappeAccount }) {
  const comp = account.subscription_source === 'comp'
  return (
    <div>
      <PlanBadge plan={account.plan} />
      {comp && <p className="mt-0.5 text-[10px] text-zinc-500">{account.comped_until ? `Free until ${fmtDate(account.comped_until)}` : 'Free, no end date'}</p>}
      {account.subscription_source === 'stripe' && <p className="mt-0.5 text-[10px] text-zinc-500">Paying · {account.subscription_status}</p>}
    </div>
  )
}

const COMP_LENGTHS = [
  { value: 'none', label: 'No end date' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: '1 year' },
  { value: 'date', label: 'Until a date…' },
] as const

function compEnd(length: string, date: string): string | null {
  if (length === 'none') return null
  if (length === 'date') return date ? new Date(`${date}T23:59:59`).toISOString() : null
  return new Date(Date.now() + Number(length) * 86_400_000).toISOString()
}

// Upgrade or downgrade an account by hand. Every plan but Free is given free
// (a comp): the account is never charged for it, and drops to Free on the end
// date. An account paying through Stripe has to be changed in Stripe.
function ChangePlanModal({ account, plans, onClose, onSaved }: { account: CappeAccount; plans: CappePlanOption[] | null; onClose: () => void; onSaved: () => void }) {
  const { toast } = useToast()
  const [planCode, setPlanCode] = useState(account.plan)
  const [length, setLength] = useState<string>('30')
  const [date, setDate] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const paying = account.subscription_source === 'stripe'
  const toFree = planCode === 'free'

  async function save() {
    if (!toFree && length === 'date' && !date) {
      toast('Pick the date the free plan ends', 'error')
      return
    }
    setSaving(true)
    try {
      await api.post(`/cappe/matcha-admin/accounts/${account.id}/plan`, {
        plan_code: planCode,
        until: toFree ? null : compEnd(length, date),
        reason: reason.trim() || null,
      })
      toast(`${account.name || account.email} is now on ${PLAN_LABEL[planCode as Exclude<PlanFilter, 'all'>] ?? planCode}`, 'success')
      onSaved()
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Plan change failed', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={`Change plan · ${account.name || account.email}`} width="sm">
      <div className="space-y-4">
        {paying ? (
          <p className="text-sm text-amber-300">This account pays through Stripe ({account.subscription_status}). Change or cancel its subscription in Stripe; changing it here would leave Stripe billing for the old plan.</p>
        ) : (
          <>
            <Select label="Plan" value={planCode} onChange={(event) => setPlanCode(event.target.value)} disabled={!plans}
              options={(plans?.length ? plans : [{ code: account.plan, name: PLAN_LABEL[account.plan as Exclude<PlanFilter, 'all'>] ?? account.plan, status: 'active' }])
                .map((plan) => ({ value: plan.code, label: plan.status === 'legacy' ? `${plan.name} (legacy)` : plan.name }))} />
            {toFree ? (
              <p className="text-xs text-zinc-500">Ends any free plan they were given. Their sites stay; paid features switch off until they subscribe.</p>
            ) : (
              <>
                <Select label="Free for" value={length} onChange={(event) => setLength(event.target.value)} options={COMP_LENGTHS} />
                {length === 'date' && <Input label="Ends on" type="date" value={date} min={new Date().toISOString().slice(0, 10)} onChange={(event) => setDate(event.target.value)} />}
                <p className="text-xs text-zinc-500">They aren't charged for it. {length === 'none' ? 'It lasts until you change it.' : 'When it ends they drop to Free and have to subscribe to keep the plan.'}</p>
              </>
            )}
            <Input label="Reason (optional)" maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
          </>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          {!paying && <Button variant="primary" disabled={saving || !plans} onClick={save}>{saving ? 'Saving…' : 'Save plan'}</Button>}
        </div>
      </div>
    </Modal>
  )
}

function statusBadgeClass(status: string) {
  if (status === 'active' || status === 'published') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
  if (status === 'suspended') return 'border-red-500/40 bg-red-500/10 text-red-300'
  if (status === 'draft') return 'border-amber-500/40 bg-amber-500/10 text-amber-300'
  return 'border-zinc-600 bg-zinc-700/30 text-zinc-400'
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] capitalize ${statusBadgeClass(status)}`}>{status}</span>
}

const money = (cents: number) => `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
const fmtDate = (iso: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'

function siteUrl(site: CappeSite): string | null {
  if (!site.custom_domain && !site.subdomain && !site.slug) return null
  return `https://${cappeSiteHost(site)}`
}

function accountMatches(account: CappeAccount, search: string) {
  const query = search.trim().toLowerCase()
  if (!query) return true
  return account.email.toLowerCase().includes(query)
    || (account.name?.toLowerCase().includes(query) ?? false)
    || account.sites.some((site) => site.name.toLowerCase().includes(query) || site.slug.toLowerCase().includes(query))
}

export default function Cappe() {
  const { toast } = useToast()
  const [params, setParams] = useSearchParams()
  const requestedView = params.get('view')
  const view: View = requestedView === 'brands' || requestedView === 'creators' || requestedView === 'grants' ? requestedView : 'websites'
  const [accounts, setAccounts] = useState<CappeAccount[]>([])
  const [totals, setTotals] = useState<CappeTotals | null>(null)
  const [plan, setPlan] = useState<PlanFilter>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [suspendTarget, setSuspendTarget] = useState<CappeAccount | null>(null)
  const [suspendNote, setSuspendNote] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [planTarget, setPlanTarget] = useState<CappeAccount | null>(null)
  // The plan picker's options, shared by the plan modal and the signup links.
  const [plans, setPlans] = useState<CappePlanOption[] | null>(null)

  useEffect(() => {
    api.get<CappePlanOption[]>('/cappe/matcha-admin/plans')
      .then(setPlans)
      .catch(() => setPlans([]))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    api.get<CappeListResponse>('/admin/cappe/accounts')
      .then((response) => { setAccounts(response.accounts); setTotals(response.totals) })
      .catch(() => { setAccounts([]); setTotals(null) })
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const creatorsCount = useMemo(() => accounts.filter((account) => account.account_type === 'creator').length, [accounts])
  const brands = useMemo(() => accounts.filter((account) => account.account_type === 'business'), [accounts])
  const websiteAccounts = useMemo(() => accounts.filter((account) => account.account_type !== 'creator' || account.sites.length > 0), [accounts])

  const filteredWebsites = useMemo(() => websiteAccounts.filter((account) => {
    if (plan !== 'all' && account.plan !== plan) return false
    return accountMatches(account, search)
  }), [websiteAccounts, plan, search])

  const filteredBrands = useMemo(
    () => brands.filter((account) => accountMatches(account, search)),
    [brands, search],
  )

  const brandStats = useMemo(() => ({
    active: brands.filter((brand) => brand.status === 'active').length,
    campaigns: brands.reduce((sum, brand) => sum + brand.campaign_count, 0),
    collabs: brands.reduce((sum, brand) => sum + brand.active_collabs, 0),
    spend: brands.reduce((sum, brand) => sum + brand.collab_spend_cents, 0),
  }), [brands])

  function changeView(next: View) {
    setSearch('')
    setParams(next === 'websites' ? {} : { view: next })
  }

  function toggle(id: string) {
    setExpanded((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function suspendAccount() {
    if (!suspendTarget) return
    setBusyId(suspendTarget.id)
    try {
      await api.post(`/admin/cappe/accounts/${suspendTarget.id}/suspend`, { note: suspendNote.trim() || null })
      setAccounts((previous) => previous.map((account) => account.id === suspendTarget.id ? { ...account, status: 'suspended' } : account))
      toast(`${suspendTarget.name || suspendTarget.email} suspended`, 'success')
      setSuspendTarget(null)
      setSuspendNote('')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Account suspension failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function restoreAccount(account: CappeAccount) {
    setBusyId(account.id)
    try {
      await api.post(`/admin/cappe/accounts/${account.id}/restore`)
      setAccounts((previous) => previous.map((item) => item.id === account.id ? { ...item, status: 'active' } : item))
      toast(`${account.name || account.email} restored`, 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Account restore failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <AdminPageHeader title="Gummfit" description="Manage websites, brand accounts, creators, marketplace reviews, and collaborations." />

      <div className="mt-6">
        <PillTabs
          options={[
            { value: 'websites', label: `Websites${totals ? ` (${totals.site_count})` : ''}` },
            { value: 'brands', label: `Brands${brands.length ? ` (${brands.length})` : ''}` },
            { value: 'creators', label: `Creators${creatorsCount ? ` (${creatorsCount})` : ''}` },
            { value: 'grants', label: 'Signup links' },
          ]}
          value={view}
          onChange={changeView}
        />
      </div>

      {view === 'creators' ? (
        <div className="mt-7"><CappeCreators /></div>
      ) : view === 'grants' ? (
        <div className="mt-7"><CappeSignupGrants plans={plans} /></div>
      ) : loading ? (
        <p className="mt-7 text-sm text-zinc-500">Loading…</p>
      ) : view === 'brands' ? (
        <div className="mt-7">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Brand accounts" value={brands.length} />
            <Stat label="Active" value={brandStats.active} />
            <Stat label="Campaigns" value={brandStats.campaigns} />
            <Stat label="Active collabs" value={brandStats.collabs} />
            <Stat label="Creator spend" value={money(brandStats.spend)} />
          </div>

          <div className="mt-6 max-w-sm">
            <Input label="" placeholder="Search brand name or email…" value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>

          <div className="mt-6">
            <AdminTable className="min-w-[900px]">
              <thead >
                <tr>
                  <th >Brand</th>
                  <th >Status</th>
                  <th >Email</th>
                  <th className="text-right">Campaigns</th>
                  <th className="text-right">Offers</th>
                  <th className="text-right">Active</th>
                  <th className="text-right">Spend</th>
                  <th >Joined</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody >
                {filteredBrands.map((brand) => (
                  <tr key={brand.id} className="text-zinc-300 hover:bg-zinc-900/30">
                    <td >
                      <p className="font-medium text-zinc-100">{brand.name || brand.email}</p>
                      <div className="mt-1 flex items-center gap-1.5"><PlanBadge plan={brand.plan} />{brand.site_count > 0 && <span className="text-[10px] text-zinc-500">{brand.site_count} site{brand.site_count === 1 ? '' : 's'}</span>}</div>
                    </td>
                    <td ><StatusBadge status={brand.status} /></td>
                    <td >
                      <p className="text-zinc-400">{brand.email}</p>
                      <p className={`mt-0.5 text-[10px] ${brand.email_verified_at ? 'text-emerald-400' : 'text-amber-400'}`}>{brand.email_verified_at ? 'Verified' : 'Unverified'}</p>
                    </td>
                    <td className="text-right tabular-nums">{brand.campaign_count}</td>
                    <td className="text-right tabular-nums">{brand.offers_sent}</td>
                    <td className="text-right tabular-nums">{brand.active_collabs}</td>
                    <td className="text-right tabular-nums">{brand.collab_spend_cents ? money(brand.collab_spend_cents) : '—'}</td>
                    <td className="text-zinc-400">{fmtDate(brand.created_at)}</td>
                    <td className="text-right whitespace-nowrap">
                      <Button size="sm" variant="ghost" onClick={() => setPlanTarget(brand)}>Plan</Button>
                      {brand.status === 'active' ? (
                        <Button size="sm" variant="ghost" disabled={busyId === brand.id} onClick={() => { setSuspendTarget(brand); setSuspendNote('') }}>Suspend</Button>
                      ) : brand.status === 'suspended' ? (
                        <Button size="sm" variant="secondary" disabled={busyId === brand.id} onClick={() => restoreAccount(brand)}>Restore</Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {filteredBrands.length === 0 && <tr><td colSpan={9} className="text-center text-zinc-500">No brand accounts found.</td></tr>}
              </tbody>
            </AdminTable>
          </div>
        </div>
      ) : (
        <div className="mt-7">
          {totals && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <Stat label="Accounts" value={totals.account_count} />
              <Stat label="Sites" value={totals.site_count} />
              <Stat label="Published" value={totals.published_count} />
              <Stat label="Orders" value={totals.order_count} />
              <Stat label="Revenue" value={money(totals.revenue_cents)} />
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Input label="" placeholder="Search email, name or site…" value={search} onChange={(event) => setSearch(event.target.value)} className="max-w-xs" />
            <AdminTabBar className="ml-auto">
              <span className="mr-2 text-[10px] uppercase tracking-wider text-zinc-500">Plan</span>
              {(['all', 'free', 'creator', 'business', 'hosting', 'pro'] as const).map((item) => (
                <AdminTab key={item} onClick={() => setPlan(item)}  active={plan === item}>
                  {item === 'all' ? 'All' : PLAN_LABEL[item]}
                </AdminTab>
              ))}
            </AdminTabBar>
          </div>

          <div className="mt-6">
            <AdminTable className="min-w-[900px]">
              <thead ><tr><th >Account</th><th >Type</th><th >Plan</th><th >Status</th><th className="text-right">Sites</th><th className="text-right">Orders</th><th className="text-right">Revenue</th><th >Joined</th><th className="text-right">Actions</th></tr></thead>
              <tbody >
                {filteredWebsites.map((account) => {
                  const isOpen = expanded.has(account.id)
                  return (
                    <Fragment key={account.id}>
                      <tr className="cursor-pointer text-zinc-300 hover:bg-zinc-900/40" onClick={() => account.site_count > 0 && toggle(account.id)}>
                        <td ><div className="flex items-center gap-2">{account.site_count > 0 ? isOpen ? <ChevronDown className="h-4 w-4 shrink-0 text-zinc-500" /> : <ChevronRight className="h-4 w-4 shrink-0 text-zinc-500" /> : <span className="h-4 w-4 shrink-0" />}<div><p className="font-medium text-zinc-100">{account.name || account.email}</p>{account.name && <p className="text-xs text-zinc-500">{account.email}</p>}</div></div></td>
                        <td ><span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] ${account.account_type === 'personal' ? 'border-sky-500/40 bg-sky-500/10 text-sky-300' : 'border-amber-500/40 bg-amber-500/10 text-amber-300'}`}>{account.account_type === 'personal' ? 'Solo' : 'Business'}</span></td>
                        <td ><PlanCell account={account} /></td><td ><StatusBadge status={account.status} /></td>
                        <td className="text-right tabular-nums">{account.site_count}{account.published_count > 0 && <span className="text-xs text-emerald-400"> · {account.published_count} live</span>}</td>
                        <td className="text-right tabular-nums">{account.order_count}</td><td className="text-right tabular-nums">{account.revenue_cents > 0 ? money(account.revenue_cents) : '—'}</td><td className="text-zinc-400">{fmtDate(account.created_at)}</td>
                        <td className="text-right"><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); setPlanTarget(account) }}>Change plan</Button></td>
                      </tr>
                      {isOpen && account.sites.map((site) => {
                        const url = siteUrl(site)
                        return <tr key={site.id} className="bg-zinc-950/40 text-zinc-400"><td className="pl-12"><div className="flex items-center gap-2"><span className="text-zinc-200">{site.name}</span>{url && <a href={url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="text-zinc-500 hover:text-emerald-400" title={url}><ExternalLink className="h-3.5 w-3.5" /></a>}</div><p className="text-xs text-zinc-600">/{site.slug} · {site.page_count} pages</p></td><td  colSpan={3}><StatusBadge status={site.status} /></td><td  /><td className="text-right tabular-nums">{site.order_count}</td><td className="text-right tabular-nums">{site.revenue_cents > 0 ? money(site.revenue_cents) : '—'}</td><td >{fmtDate(site.created_at)}</td><td /></tr>
                      })}
                    </Fragment>
                  )
                })}
                {filteredWebsites.length === 0 && <tr><td colSpan={9} className="text-center text-zinc-500">No Gummfit accounts found.</td></tr>}
              </tbody>
            </AdminTable>
          </div>
        </div>
      )}

      {planTarget && <ChangePlanModal account={planTarget} plans={plans} onClose={() => setPlanTarget(null)} onSaved={() => { setPlanTarget(null); load() }} />}

      <Modal open={suspendTarget != null} onClose={() => setSuspendTarget(null)} title={suspendTarget ? `Suspend ${suspendTarget.name || suspendTarget.email}` : ''} width="sm">
        <div className="space-y-4">
          <p className="text-sm text-zinc-400">This immediately revokes the brand’s active sessions. Their sites and collaboration records are preserved.</p>
          <Textarea label="Internal reason (optional)" value={suspendNote} onChange={(event) => setSuspendNote(event.target.value)} rows={3} />
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setSuspendTarget(null)}>Cancel</Button><Button variant="primary" disabled={busyId === suspendTarget?.id} onClick={suspendAccount}>Suspend account</Button></div>
        </div>
      </Modal>
    </div>
  )
}
