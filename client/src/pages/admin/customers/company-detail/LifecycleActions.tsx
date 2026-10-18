import { AdminButton, AdminSelect, AdminInput } from '../../../../components/admin/AdminUI'
import { useState, useEffect } from 'react'
import { api } from '../../../../api/client'
import { useAsync } from '../../../../hooks/useAsync'
import type { Registration, Charge } from './types'

type BuiltinTierOption = { slug: string; label: string; blurb: string; stripe_gate_flag: string | null }

// Sourced from GET /admin/products' `builtin_products` (feature_flags.py's
// BUILTIN_TIER_META + BUILTIN_TIER_SLUGS) — was a fourth hardcoded copy of
// tier labels that had drifted (missing matcha_lite_essentials entirely).
function tierOptionLabel(t: BuiltinTierOption): string {
  const gated = t.stripe_gate_flag
    ? ' (requires Stripe checkout or a signup link to activate)'
    : ''
  return `${t.label}${gated} — ${t.blurb}`
}

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
  const { data: tierOptions } = useAsync(
    () => api.get<{ builtin_products: BuiltinTierOption[] }>('/admin/products').then((r) => r.builtin_products),
    [],
    [] as BuiltinTierOption[],
  )

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
          <AdminButton
            onClick={passwordReset}
            disabled={busy || isDeleted || !registration.owner_user_id}
            className="disabled:opacity-40" variant="secondary"
          >
            Issue owner password reset
          </AdminButton>
          {!isDeleted ? (
            <AdminButton
              onClick={softDelete}
              disabled={busy}
              className="disabled:opacity-40" variant="danger"
            >
              Soft-delete
            </AdminButton>
          ) : (
            <AdminButton
              onClick={restore}
              disabled={busy}
              className="disabled:opacity-40" variant="success"
            >
              Restore
            </AdminButton>
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
            <AdminButton
              onClick={() => cancelSub(false)}
              disabled={busy || isDeleted || registration.subscription?.status !== 'active'}
              className="disabled:opacity-40" variant="secondary"
            >
              Cancel at period end
            </AdminButton>
            <AdminButton
              onClick={() => cancelSub(true)}
              disabled={busy || isDeleted}
              className="disabled:opacity-40" variant="danger"
            >
              Cancel immediately
            </AdminButton>
            <AdminButton
              onClick={() => setRefundOpen(true)}
              disabled={busy || isDeleted}
              className="disabled:opacity-40" variant="secondary"
            >
              Issue refund…
            </AdminButton>
          </div>
        ) : (
          <p className="text-xs text-zinc-500">No subscription. Refunds and cancellations require a Stripe customer.</p>
        )}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Tier</h3>
        <div className="flex items-center gap-2">
          <AdminSelect
            value={tierTarget}
            onChange={(e) => setTierTarget(e.target.value)}
            disabled={isDeleted}
            className="flex-1 disabled:opacity-40"
          >
            <option value="">Pick a tier…</option>
            {tierOptions.filter((t) => t.slug !== registration.signup_source).map((t) => (
              <option key={t.slug} value={t.slug}>{tierOptionLabel(t)}</option>
            ))}
          </AdminSelect>
          <AdminButton
            onClick={changeTier}
            disabled={busy || isDeleted || !tierTarget}
            className="disabled:opacity-40" variant="success"
          >
            Switch
          </AdminButton>
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
              <AdminSelect
                value={chargeId}
                onChange={(e) => setChargeId(e.target.value)} className="w-full"
              >
                <option value="">Pick a charge…</option>
                {charges.map((c) => (
                  <option key={c.id} value={c.id}>
                    ${(c.amount / 100).toFixed(2)} {c.currency.toUpperCase()} ·{' '}
                    {new Date(c.created * 1000).toLocaleDateString()} · {c.status}
                    {c.amount_refunded > 0 && ` (${(c.amount_refunded / 100).toFixed(2)} refunded)`}
                  </option>
                ))}
              </AdminSelect>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Amount (cents) — optional</label>
              <AdminInput
                value={amount}
                onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
                placeholder="full refund if blank"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Reason</label>
              <AdminSelect
                value={reason}
                onChange={(e) => setReason(e.target.value)} className="w-full"
              >
                <option value="requested_by_customer">requested_by_customer</option>
                <option value="duplicate">duplicate</option>
                <option value="fraudulent">fraudulent</option>
              </AdminSelect>
            </div>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">
            Cancel
          </button>
          <AdminButton
            type="submit"
            disabled={submitting || !chargeId}
            className="disabled:opacity-40" variant="danger"
          >
            {submitting ? 'Refunding…' : 'Refund'}
          </AdminButton>
        </div>
      </form>
    </div>
  )
}
