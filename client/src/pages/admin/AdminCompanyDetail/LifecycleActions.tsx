import { useState, useEffect } from 'react'
import { api } from '../../../api/client'
import type { Registration, Charge } from './types'

const TIER_OPTIONS = [
  { value: 'resources_free', label: 'Free (Resources only)' },
  { value: 'matcha_lite', label: 'Matcha Lite' },
  { value: 'matcha_x', label: 'Matcha-X (mid tier — requires Stripe checkout to activate)' },
  { value: 'matcha_compliance', label: 'Matcha Compliance (standalone — requires Stripe checkout or a signup link to activate)' },
  { value: 'bespoke', label: 'Platform / Bespoke (full features)' },
  { value: 'ir_only_self_serve', label: 'IR Cap (incidents + employees + discipline)' },
]

export function LifecycleActions({
  companyId,
  registration,
  onRefresh,
}: {
  companyId: string
  registration: Registration
  onRefresh: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [resetUrl, setResetUrl] = useState<string | null>(null)
  const [refundOpen, setRefundOpen] = useState(false)
  const [tierTarget, setTierTarget] = useState('')

  async function withBusy(fn: () => Promise<void>) {
    if (busy) return
    setBusy(true)
    try { await fn() } finally { setBusy(false) }
  }

  async function suspendOrUnsuspend() {
    if (!registration.owner_user_id) return
    await withBusy(async () => {
      const path = registration.is_suspended ? 'unsuspend' : 'suspend'
      await api.post(`/admin/users/${registration.owner_user_id}/${path}`, {})
      await onRefresh()
    })
  }

  async function passwordReset() {
    if (!registration.owner_user_id) return
    await withBusy(async () => {
      const res = await api.post<{ reset_url: string }>(`/admin/users/${registration.owner_user_id}/password-reset`, {})
      setResetUrl(res.reset_url)
    })
  }

  async function cancelSub(immediate: boolean) {
    await withBusy(async () => {
      const qs = immediate ? '?immediate=true' : ''
      await api.post(`/admin/companies/${companyId}/cancel-subscription${qs}`, {})
      await onRefresh()
    })
  }

  async function changeTier() {
    if (!tierTarget) return
    if (!confirm(`Switch tier to "${tierTarget}"? This rewrites enabled_features.`)) return
    await withBusy(async () => {
      await api.patch(`/admin/companies/${companyId}/tier`, { tier: tierTarget })
      await onRefresh()
    })
  }

  async function softDelete() {
    if (!confirm('Soft-delete this company? It disappears from lists; rows persist for audit.')) return
    await withBusy(async () => {
      await api.delete(`/admin/companies/${companyId}`)
      await onRefresh()
    })
  }

  async function restore() {
    await withBusy(async () => {
      await api.post(`/admin/companies/${companyId}/restore`, {})
      await onRefresh()
    })
  }

  const isDeleted = !!registration.deleted_at

  return (
    <>
      {isDeleted && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-400">
          This company is soft-deleted. Lifecycle actions are disabled until you restore it.
        </div>
      )}

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Account</h3>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={suspendOrUnsuspend}
            disabled={busy || isDeleted || !registration.owner_user_id}
            className={`text-xs px-3 py-1.5 rounded-lg disabled:opacity-40 transition-colors ${
              registration.is_suspended
                ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-200'
            }`}
          >
            {registration.is_suspended ? 'Unsuspend owner' : 'Suspend owner'}
          </button>
          <button
            onClick={passwordReset}
            disabled={busy || isDeleted || !registration.owner_user_id}
            className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
          >
            Issue owner password reset
          </button>
          {!isDeleted ? (
            <button
              onClick={softDelete}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-200 disabled:opacity-40"
            >
              Soft-delete
            </button>
          ) : (
            <button
              onClick={restore}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40"
            >
              Restore
            </button>
          )}
        </div>
        {resetUrl && (
          <div className="mt-3 p-3 rounded-lg border border-emerald-700/40 bg-emerald-900/20">
            <div className="text-[10px] text-emerald-300 uppercase tracking-wider mb-1">Reset link (1h)</div>
            <code className="text-[11px] break-all text-emerald-100">{resetUrl}</code>
            <button
              onClick={() => { navigator.clipboard?.writeText(resetUrl); }}
              className="block mt-2 text-[11px] text-emerald-300 hover:text-emerald-200"
            >
              Copy →
            </button>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Billing</h3>
        {registration.subscription ? (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => cancelSub(false)}
              disabled={busy || isDeleted || registration.subscription?.status !== 'active'}
              className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
            >
              Cancel at period end
            </button>
            <button
              onClick={() => cancelSub(true)}
              disabled={busy || isDeleted}
              className="text-xs px-3 py-1.5 rounded-lg bg-red-900/40 hover:bg-red-900/60 text-red-200 disabled:opacity-40"
            >
              Cancel immediately
            </button>
            <button
              onClick={() => setRefundOpen(true)}
              disabled={busy || isDeleted}
              className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-40"
            >
              Issue refund…
            </button>
          </div>
        ) : (
          <p className="text-xs text-zinc-500">No subscription. Refunds and cancellations require a Stripe customer.</p>
        )}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Tier</h3>
        <div className="flex items-center gap-2">
          <select
            value={tierTarget}
            onChange={(e) => setTierTarget(e.target.value)}
            disabled={isDeleted}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500 disabled:opacity-40"
          >
            <option value="">Pick a tier…</option>
            {TIER_OPTIONS.filter((t) => t.value !== registration.signup_source).map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <button
            onClick={changeTier}
            disabled={busy || isDeleted || !tierTarget}
            className="text-xs px-3 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40"
          >
            Switch
          </button>
        </div>
        <p className="text-[10px] text-zinc-600 mt-2">
          Current: <span className="font-mono text-zinc-400">{registration.signup_source ?? 'bespoke'}</span>.
          Switching rewrites enabled_features to the target tier's preset. Activating Lite, Matcha-X, or Compliance requires Stripe checkout (or a signup link) — not allowed here.
        </p>
      </section>

      {refundOpen && (
        <RefundModal
          companyId={companyId}
          onClose={() => setRefundOpen(false)}
          onDone={() => { setRefundOpen(false); onRefresh() }}
        />
      )}
    </>
  )
}

function RefundModal({
  companyId,
  onClose,
  onDone,
}: {
  companyId: string
  onClose: () => void
  onDone: () => void
}) {
  const [charges, setCharges] = useState<Charge[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chargeId, setChargeId] = useState<string>('')
  const [amount, setAmount] = useState<string>('')
  const [reason, setReason] = useState<string>('requested_by_customer')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.get<{ charges: Charge[] }>(`/admin/companies/${companyId}/charges`)
      .then((r) => setCharges(r.charges))
      .catch((e) => setError(e?.message ?? 'Failed to load charges'))
  }, [companyId])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!chargeId) return
    setSubmitting(true)
    setError(null)
    try {
      const body: { charge_id: string; amount_cents?: number; reason?: string } = { charge_id: chargeId }
      if (amount.trim()) body.amount_cents = parseInt(amount, 10)
      if (reason) body.reason = reason
      await api.post(`/admin/companies/${companyId}/refund`, body)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refund failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <form onSubmit={submit} className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-lg">
        <h3 className="text-sm font-semibold text-zinc-100 mb-1">Issue refund</h3>
        <p className="text-xs text-zinc-500 mb-4">Pick a charge. Leave amount blank for a full refund.</p>
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Charge</label>
            {charges === null ? (
              <p className="text-xs text-zinc-500">Loading charges…</p>
            ) : charges.length === 0 ? (
              <p className="text-xs text-zinc-500">No charges on this customer yet.</p>
            ) : (
              <select
                value={chargeId}
                onChange={(e) => setChargeId(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
              >
                <option value="">Pick a charge…</option>
                {charges.map((c) => (
                  <option key={c.id} value={c.id}>
                    ${(c.amount / 100).toFixed(2)} {c.currency.toUpperCase()} ·{' '}
                    {new Date(c.created * 1000).toLocaleDateString()} · {c.status}
                    {c.amount_refunded > 0 && ` (${(c.amount_refunded / 100).toFixed(2)} refunded)`}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Amount (cents) — optional</label>
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
                placeholder="full refund if blank"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Reason</label>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-zinc-500"
              >
                <option value="requested_by_customer">requested_by_customer</option>
                <option value="duplicate">duplicate</option>
                <option value="fraudulent">fraudulent</option>
              </select>
            </div>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !chargeId}
            className="text-xs px-3 py-1.5 rounded-lg bg-red-900/50 hover:bg-red-900/70 text-red-200 disabled:opacity-40"
          >
            {submitting ? 'Refunding…' : 'Refund'}
          </button>
        </div>
      </form>
    </div>
  )
}
