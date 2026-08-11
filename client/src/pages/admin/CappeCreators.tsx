import { Fragment, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, ExternalLink, XCircle } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Input, Modal, PillTabs, Select, Textarea, useToast } from '../../components/ui'

type CreatorSocial = {
  id: string
  platform: string
  handle: string
  url: string
  follower_count: number | null
  verified_follower_count: number | null
  audit_status: 'unverified' | 'verified' | 'flagged'
  audited_at: string | null
  audit_note: string | null
}

type CreatorRow = {
  id: string
  handle: string
  display_name: string | null
  avatar_url: string | null
  status: 'draft' | 'pending_review' | 'published' | 'rejected' | 'suspended'
  review_note: string | null
  niches: string[]
  location: string | null
  open_to_offers: boolean
  reach_verified: boolean
  reach_audited_at: string | null
  submitted_at: string | null
  published_at: string | null
  created_at: string
  account_id: string
  account_status: string
  email: string
  account_name: string | null
  socials: CreatorSocial[]
  reaudit_due: boolean
}

type MarketplaceSettings = {
  collab_fee_bps: number
  min_offer_cents: number
  auto_approve_days: number
}

type CollabOverview = {
  by_status: { status: string; n: number; total_cents: number }[]
  gmv_cents: number
  fees_cents: number
  brands: {
    brand_account_id: string
    brand_name: string | null
    brand_email: string
    offers_sent: number
    completed: number
    in_progress: number
    brand_cancelled: number
    avg_hours_to_pay: number | null
  }[]
}

type Tab = 'queue' | 'all' | 'reaudit' | 'settings' | 'collabs'

const money = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'

const STATUS_BADGE: Record<string, string> = {
  draft: 'border-zinc-600 bg-zinc-700/30 text-zinc-400',
  pending_review: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  published: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  rejected: 'border-red-500/40 bg-red-500/10 text-red-300',
  suspended: 'border-red-500/40 bg-red-500/10 text-red-300',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border capitalize ${STATUS_BADGE[status] ?? STATUS_BADGE.draft}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-zinc-100">{value}</p>
    </div>
  )
}

export default function CappeCreators({ embedded = false }: { embedded?: boolean }) {
  const { toast } = useToast()
  const [tab, setTab] = useState<Tab>('queue')
  const [creators, setCreators] = useState<CreatorRow[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const [rejectTarget, setRejectTarget] = useState<CreatorRow | null>(null)
  const [rejectNote, setRejectNote] = useState('')
  const [auditTarget, setAuditTarget] = useState<{ profileId: string; social: CreatorSocial } | null>(null)
  const [auditStatus, setAuditStatus] = useState<'verified' | 'flagged' | 'unverified'>('unverified')
  const [auditCount, setAuditCount] = useState('')
  const [auditNote, setAuditNote] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  const [settings, setSettings] = useState<MarketplaceSettings | null>(null)
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [feePct, setFeePct] = useState('')
  const [minOfferDollars, setMinOfferDollars] = useState('')
  const [autoApproveDays, setAutoApproveDays] = useState('')
  const [savingSettings, setSavingSettings] = useState(false)

  const [overview, setOverview] = useState<CollabOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)

  function load() {
    setLoading(true)
    api.get<CreatorRow[]>('/admin/cappe/creators')
      .then(setCreators)
      .catch(() => setCreators([]))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  useEffect(() => {
    if (tab === 'settings' && !settings && !settingsLoading) {
      setSettingsLoading(true)
      api.get<MarketplaceSettings>('/admin/cappe/marketplace-settings')
        .then((s) => {
          setSettings(s)
          setFeePct(String(s.collab_fee_bps / 100))
          setMinOfferDollars(String(s.min_offer_cents / 100))
          setAutoApproveDays(String(s.auto_approve_days))
        })
        .catch(() => toast('Could not load settings', 'error'))
        .finally(() => setSettingsLoading(false))
    }
    if (tab === 'collabs' && !overview && !overviewLoading) {
      setOverviewLoading(true)
      api.get<CollabOverview>('/admin/cappe/collab-overview')
        .then(setOverview)
        .catch(() => toast('Could not load collab overview', 'error'))
        .finally(() => setOverviewLoading(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const queue = useMemo(() => creators.filter((c) => c.status === 'pending_review'), [creators])
  const reaudit = useMemo(
    () => [...creators.filter((c) => c.reaudit_due)].sort((a, b) => (a.reach_audited_at ?? '').localeCompare(b.reach_audited_at ?? '')),
    [creators],
  )

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function approve(row: CreatorRow) {
    setBusyId(row.id)
    try {
      await api.post(`/admin/cappe/creators/${row.id}/approve`)
      toast(`@${row.handle} approved`, 'success')
      setCreators((prev) => prev.map((c) => (c.id === row.id
        ? {
            ...c, status: 'published', review_note: null,
            published_at: c.published_at ?? new Date().toISOString(),
            reaudit_due: c.socials.length > 0 && c.reach_audited_at === null,
          }
        : c)))
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Approve failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function submitReject() {
    if (!rejectTarget || !rejectNote.trim()) return
    setBusyId(rejectTarget.id)
    try {
      await api.post(`/admin/cappe/creators/${rejectTarget.id}/reject`, { note: rejectNote.trim() })
      toast(`@${rejectTarget.handle} rejected`, 'success')
      const note = rejectNote.trim()
      setCreators((prev) => prev.map((c) => (c.id === rejectTarget.id ? { ...c, status: 'rejected', review_note: note } : c)))
      setRejectTarget(null)
      setRejectNote('')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Reject failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function suspend(row: CreatorRow) {
    const note = window.prompt(`Suspend @${row.handle} — note (optional):`)
    if (note === null) return
    setBusyId(row.id)
    try {
      await api.post(`/admin/cappe/creators/${row.id}/suspend`, { note: note || null })
      toast(`@${row.handle} suspended`, 'success')
      setCreators((prev) => prev.map((c) => (c.id === row.id ? { ...c, status: 'suspended', review_note: note || null } : c)))
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Suspend failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function restore(row: CreatorRow) {
    setBusyId(row.id)
    try {
      await api.post(`/admin/cappe/creators/${row.id}/restore`)
      toast(`@${row.handle} restored`, 'success')
      setCreators((prev) => prev.map((c) => (c.id === row.id ? { ...c, status: 'published', review_note: null } : c)))
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Restore failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function suspendAccount(row: CreatorRow) {
    const note = window.prompt(`Disable login for ${row.email} — note (optional):`)
    if (note === null) return
    setBusyId(row.account_id)
    try {
      await api.post(`/admin/cappe/accounts/${row.account_id}/suspend`, { note: note || null })
      toast(`${row.email} suspended`, 'success')
      setCreators((prev) => prev.map((c) => (c.account_id === row.account_id ? { ...c, account_status: 'suspended' } : c)))
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Account suspension failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function restoreAccount(row: CreatorRow) {
    setBusyId(row.account_id)
    try {
      await api.post(`/admin/cappe/accounts/${row.account_id}/restore`)
      toast(`${row.email} restored`, 'success')
      setCreators((prev) => prev.map((c) => (c.account_id === row.account_id ? { ...c, account_status: 'active' } : c)))
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Account restore failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  function openAudit(profileId: string, social: CreatorSocial) {
    setAuditTarget({ profileId, social })
    setAuditStatus(social.audit_status)
    setAuditCount(social.verified_follower_count != null ? String(social.verified_follower_count) : '')
    setAuditNote(social.audit_note ?? '')
  }

  async function submitAudit() {
    if (!auditTarget) return
    if (auditStatus === 'verified' && !auditCount.trim()) return
    setBusyId(auditTarget.social.id)
    try {
      await api.post(`/admin/cappe/creators/socials/${auditTarget.social.id}/audit`, {
        audit_status: auditStatus,
        verified_follower_count: auditCount.trim() ? Number(auditCount) : null,
        note: auditNote.trim() || null,
      })
      toast('Social audited', 'success')
      setAuditTarget(null)
      load()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Audit failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function saveSettings() {
    setSavingSettings(true)
    try {
      const body = {
        collab_fee_bps: Math.round(Number(feePct) * 100),
        min_offer_cents: Math.round(Number(minOfferDollars) * 100),
        auto_approve_days: Number(autoApproveDays),
      }
      await api.patch('/admin/cappe/marketplace-settings', body)
      setSettings(body)
      toast('Settings saved', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Save failed', 'error')
    } finally {
      setSavingSettings(false)
    }
  }

  function CreatorTable({ rows }: { rows: CreatorRow[] }) {
    if (rows.length === 0) return <p className="text-sm text-zinc-500">Nothing here.</p>
    return (
      <div className="overflow-hidden rounded-xl border border-zinc-800">
        <table className="w-full text-sm text-left">
          <thead className="bg-zinc-900/50 text-zinc-400">
            <tr>
              <th className="px-4 py-3 font-medium">Creator</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Socials</th>
              <th className="px-4 py-3 font-medium">Niches</th>
              <th className="px-4 py-3 font-medium">Submitted</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {rows.map((row) => {
              const isOpen = expanded.has(row.id)
              return (
                <Fragment key={row.id}>
                  <tr className="cursor-pointer text-zinc-300 hover:bg-zinc-900/40" onClick={() => toggle(row.id)}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {isOpen ? <ChevronDown className="h-4 w-4 shrink-0 text-zinc-500" /> : <ChevronRight className="h-4 w-4 shrink-0 text-zinc-500" />}
                        <div>
                          <p className="font-medium text-zinc-100">@{row.handle} {row.reach_verified && <CheckCircle2 className="inline h-3.5 w-3.5 text-emerald-400" />}</p>
                          <p className="text-xs text-zinc-500">{row.display_name || row.account_name || row.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={row.status} /></td>
                    <td className="px-4 py-3 text-zinc-400">{row.socials.length}</td>
                    <td className="px-4 py-3 text-zinc-400">{row.niches.slice(0, 2).join(', ')}{row.niches.length > 2 ? '…' : ''}</td>
                    <td className="px-4 py-3 text-zinc-400">{fmtDate(row.submitted_at)}</td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-2">
                        {row.status === 'pending_review' && (
                          <>
                            <Button size="sm" variant="primary" disabled={busyId === row.id} onClick={() => approve(row)}>
                              <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                            </Button>
                            <Button size="sm" variant="ghost" disabled={busyId === row.id} onClick={() => { setRejectTarget(row); setRejectNote('') }}>
                              <XCircle className="h-3.5 w-3.5" /> Reject
                            </Button>
                          </>
                        )}
                        {row.status === 'published' && (
                          <Button size="sm" variant="ghost" disabled={busyId === row.id} onClick={() => suspend(row)}>Suspend</Button>
                        )}
                        {row.status === 'suspended' && (
                          <Button size="sm" variant="secondary" disabled={busyId === row.id} onClick={() => restore(row)}>Restore</Button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-zinc-950/40">
                      <td colSpan={6} className="px-4 py-3">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/30 px-3 py-2">
                          <div>
                            <p className="text-xs font-medium text-zinc-300">{row.email}</p>
                            <p className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-500">Account {row.account_status}</p>
                          </div>
                          {row.account_status === 'active' ? (
                            <Button size="sm" variant="ghost" disabled={busyId === row.account_id} onClick={() => suspendAccount(row)}>Disable login</Button>
                          ) : row.account_status === 'suspended' ? (
                            <Button size="sm" variant="secondary" disabled={busyId === row.account_id} onClick={() => restoreAccount(row)}>Restore login</Button>
                          ) : null}
                        </div>
                        {row.review_note && (
                          <p className="mb-2 text-xs text-zinc-500">Note: {row.review_note}</p>
                        )}
                        <div className="space-y-1.5">
                          {row.socials.length === 0 && <p className="text-xs text-zinc-600">No socials added.</p>}
                          {row.socials.map((s) => (
                            <div key={s.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 px-3 py-2 text-xs">
                              <div className="flex items-center gap-2">
                                <span className="capitalize text-zinc-300">{s.platform}</span>
                                <a href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-zinc-500 hover:text-emerald-400">
                                  @{s.handle} <ExternalLink className="h-3 w-3" />
                                </a>
                                <span className="text-zinc-600">{s.follower_count != null ? `${s.follower_count.toLocaleString()} followers (self-reported)` : ''}</span>
                                <span className={`rounded border px-1.5 py-0.5 capitalize ${
                                  s.audit_status === 'verified' ? 'border-emerald-500/40 text-emerald-300'
                                  : s.audit_status === 'flagged' ? 'border-red-500/40 text-red-300'
                                  : 'border-zinc-600 text-zinc-400'
                                }`}>{s.audit_status}</span>
                              </div>
                              <Button size="sm" variant="ghost" onClick={() => openAudit(row.id, s)}>Audit</Button>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div>
      {!embedded && (
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Cappe Creators</h1>
          <p className="mt-2 text-sm text-zinc-500">Creator marketplace review queue, roster, social audits, and collab settings.</p>
        </div>
      )}

      <div className={embedded ? '' : 'mt-6'}>
        <PillTabs
          options={[
            { value: 'queue', label: `Review queue${queue.length ? ` (${queue.length})` : ''}` },
            { value: 'all', label: 'All creators' },
            { value: 'reaudit', label: `Re-audit due${reaudit.length ? ` (${reaudit.length})` : ''}` },
            { value: 'settings', label: 'Settings' },
            { value: 'collabs', label: 'Collabs' },
          ]}
          value={tab}
          onChange={setTab}
        />
      </div>

      <div className="mt-6">
        {loading && tab !== 'settings' && tab !== 'collabs' ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : tab === 'queue' ? (
          <CreatorTable rows={queue} />
        ) : tab === 'all' ? (
          <CreatorTable rows={creators} />
        ) : tab === 'reaudit' ? (
          <CreatorTable rows={reaudit} />
        ) : tab === 'settings' ? (
          settingsLoading || !settings ? (
            <p className="text-sm text-zinc-500">Loading…</p>
          ) : (
            <div className="max-w-sm space-y-4">
              <Input label="Collab fee (%)" type="number" min={0} max={50} step={0.25} value={feePct} onChange={(e) => setFeePct(e.target.value)} />
              <Input label="Minimum offer ($)" type="number" min={0} step={1} value={minOfferDollars} onChange={(e) => setMinOfferDollars(e.target.value)} />
              <Input label="Auto-approve after (days)" type="number" min={1} max={90} step={1} value={autoApproveDays} onChange={(e) => setAutoApproveDays(e.target.value)} />
              <p className="text-xs text-zinc-500">Fee applies to new checkout sessions immediately; paid installments keep their snapshotted fee.</p>
              <Button variant="primary" disabled={savingSettings} onClick={saveSettings}>Save</Button>
            </div>
          )
        ) : (
          overviewLoading || !overview ? (
            <p className="text-sm text-zinc-500">Loading…</p>
          ) : (
            <div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="GMV" value={money(overview.gmv_cents)} />
                <Stat label="Fees collected" value={money(overview.fees_cents)} />
                {overview.by_status.map((s) => (
                  <Stat key={s.status} label={s.status.replace('_', ' ')} value={s.n} />
                ))}
              </div>

              <h2 className="mt-6 mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">By brand</h2>
              <div className="overflow-hidden rounded-xl border border-zinc-800">
                <table className="w-full text-sm text-left">
                  <thead className="bg-zinc-900/50 text-zinc-400">
                    <tr>
                      <th className="px-4 py-3 font-medium">Brand</th>
                      <th className="px-4 py-3 font-medium text-right">Offers sent</th>
                      <th className="px-4 py-3 font-medium text-right">Completed</th>
                      <th className="px-4 py-3 font-medium text-right">In progress</th>
                      <th className="px-4 py-3 font-medium text-right">Brand-cancelled</th>
                      <th className="px-4 py-3 font-medium text-right">Avg hrs to pay</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {overview.brands.map((b) => (
                      <tr key={b.brand_account_id} className="text-zinc-300">
                        <td className="px-4 py-2.5">
                          <p className="font-medium text-zinc-100">{b.brand_name || b.brand_email}</p>
                          {b.brand_name && <p className="text-xs text-zinc-500">{b.brand_email}</p>}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{b.offers_sent}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{b.completed}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{b.in_progress}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {b.brand_cancelled}
                          {b.offers_sent > 0 && b.brand_cancelled > 0 && (
                            <span className="ml-1 text-xs text-red-400">({Math.round((b.brand_cancelled / b.offers_sent) * 100)}%)</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{b.avg_hours_to_pay != null ? Math.round(b.avg_hours_to_pay) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        )}
      </div>

      <Modal open={rejectTarget != null} onClose={() => setRejectTarget(null)} title={rejectTarget ? `Reject @${rejectTarget.handle}` : ''} width="sm">
        <div className="space-y-4">
          <Textarea label="Reason (shown to the creator)" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} rows={4} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setRejectTarget(null)}>Cancel</Button>
            <Button variant="primary" disabled={!rejectNote.trim() || busyId === rejectTarget?.id} onClick={submitReject}>Reject</Button>
          </div>
        </div>
      </Modal>

      <Modal open={auditTarget != null} onClose={() => setAuditTarget(null)} title={auditTarget ? `Audit @${auditTarget.social.platform} — ${auditTarget.social.handle}` : ''} width="sm">
        {auditTarget && (
          <div className="space-y-4">
            <a href={auditTarget.social.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300">
              Open profile <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <p className="text-xs text-zinc-500">
              Self-reported: {auditTarget.social.follower_count != null ? auditTarget.social.follower_count.toLocaleString() : 'unknown'} followers
            </p>
            <Select
              label="Audit status"
              value={auditStatus}
              onChange={(e) => setAuditStatus(e.target.value as typeof auditStatus)}
              options={[
                { value: 'unverified', label: 'Unverified' },
                { value: 'verified', label: 'Verified' },
                { value: 'flagged', label: 'Flagged' },
              ]}
            />
            <Input
              label={`Verified follower count${auditStatus === 'verified' ? ' (required)' : ''}`}
              type="number" min={0} value={auditCount} onChange={(e) => setAuditCount(e.target.value)}
            />
            <Textarea label="Note (optional)" value={auditNote} onChange={(e) => setAuditNote(e.target.value)} rows={3} />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setAuditTarget(null)}>Cancel</Button>
              <Button
                variant="primary"
                disabled={(auditStatus === 'verified' && !auditCount.trim()) || busyId === auditTarget.social.id}
                onClick={submitAudit}
              >
                Save
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
