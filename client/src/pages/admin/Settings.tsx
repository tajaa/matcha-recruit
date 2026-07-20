import { useState, useEffect } from 'react'
import { Card } from '../../components/ui'
import { Button } from '../../components/ui'
import { Loader2, Trash2, Plus, RefreshCw, Send } from 'lucide-react'
import { useAsync } from '../../hooks/useAsync'
import {
  adminSettingsApi,
  type TokenQuota,
  type TokenUsage,
  type BetaInvitation,
} from '../../api/admin/platformSettings'

const RESEARCH_MODELS = [
  { id: 'lite', label: 'Lite', model: 'Gemini 3.1 Flash Lite', description: 'Fastest, lowest cost — good for bulk research' },
  { id: 'light', label: 'Light', model: 'Gemini 3 Flash', description: 'Balanced speed and quality (default)' },
  { id: 'heavy', label: 'Pro', model: 'Gemini 3.1 Pro', description: 'Highest quality, slower — best for targeted research' },
]

export default function Settings() {
  const [pendingMode, setPendingMode] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Token quotas & usage
  const [showAddQuota, setShowAddQuota] = useState(false)
  const [newQuota, setNewQuota] = useState({ user_email: '', token_limit: '100000', window_hours: '12' })
  const [quotaError, setQuotaError] = useState('')

  // Beta invitations
  const [betaEmails, setBetaEmails] = useState('')
  const [betaSending, setBetaSending] = useState(false)
  const [betaResult, setBetaResult] = useState<string | null>(null)

  // 'light' is the documented default when the row is unset. The old code also
  // fell back to it on a FAILED fetch, which quietly told the admin the mode was
  // Light when it might be anything — useAsync keeps failure as `error` instead.
  const settings = useAsync(() => adminSettingsApi.getPlatformSettings(), [])
  const researchMode = settings.data?.jurisdiction_research_model_mode ?? null

  // Seed the pending selection once the saved value arrives, without clobbering
  // a choice the admin has already made while it was in flight.
  useEffect(() => {
    if (researchMode && pendingMode === null) setPendingMode(researchMode)
  }, [researchMode, pendingMode])

  const quotaState = useAsync<{ quotas: TokenQuota[]; usage: TokenUsage[] }>(
    async () => {
      const [quotas, usage] = await Promise.all([
        adminSettingsApi.listQuotas(),
        adminSettingsApi.listUsage(),
      ])
      return { quotas, usage }
    },
    [],
    { quotas: [], usage: [] },
  )
  const { quotas, usage } = quotaState.data
  const quotaLoading = quotaState.loading

  const beta = useAsync<BetaInvitation[]>(() => adminSettingsApi.listBetaInvitations(), [], [])
  const betaInvites = beta.data
  const betaLoading = beta.loading

  async function handleSave() {
    if (!pendingMode || pendingMode === researchMode) return
    setSaving(true)
    try {
      await adminSettingsApi.setResearchModelMode(pendingMode)
      settings.setData({ jurisdiction_research_model_mode: pendingMode })
    } finally { setSaving(false) }
  }

  async function handleUpdateQuota(id: string, updates: Record<string, unknown>) {
    await adminSettingsApi.updateQuota(id, updates)
    await quotaState.reload()
  }

  async function handleDeleteQuota(id: string) {
    await adminSettingsApi.deleteQuota(id)
    await quotaState.reload()
  }

  async function handleAddQuota() {
    setQuotaError('')
    const body: Record<string, unknown> = {
      token_limit: parseInt(newQuota.token_limit) || 100000,
      window_hours: parseInt(newQuota.window_hours) || 12,
    }
    // If email provided, look up user_id
    if (newQuota.user_email.trim()) {
      body.user_email = newQuota.user_email.trim()
      // We'll let the backend resolve the email — but current endpoint takes user_id.
      // For now, find user_id from usage data or just pass null for global.
      const match = usage.find((u) => u.email === newQuota.user_email.trim())
      if (match) {
        body.user_id = match.user_id
      } else {
        setQuotaError('User not found in recent usage. Enter the exact email.')
        return
      }
    }
    try {
      await adminSettingsApi.createQuota(body)
    } catch (e) {
      // Previously `if (res.ok)` — a rejected quota just did nothing and left
      // the form open with no explanation.
      setQuotaError(e instanceof Error ? e.message : String(e))
      return
    }
    setShowAddQuota(false)
    setNewQuota({ user_email: '', token_limit: '100000', window_hours: '12' })
    await quotaState.reload()
  }

  async function handleSendBetaInvites() {
    const emails = betaEmails
      .split(/[\n,;]+/)
      .map((e) => e.trim().toLowerCase())
      .filter((e) => e.includes('@'))
    if (emails.length === 0) return
    setBetaSending(true)
    setBetaResult(null)
    try {
      const data = await adminSettingsApi.sendBetaInvitations(emails)
      setBetaResult(`Sent ${data.sent} invitation${data.sent !== 1 ? 's' : ''}${data.skipped?.length ? `. Skipped: ${data.skipped.join(', ')}` : ''}`)
      setBetaEmails('')
      await beta.reload()
    } catch (e) {
      setBetaResult(e instanceof Error ? e.message : String(e))
    } finally {
      setBetaSending(false)
    }
  }

  async function handleRevokeBetaInvite(id: string) {
    await adminSettingsApi.revokeBetaInvitation(id)
    await beta.reload()
  }

  const hasChanges = pendingMode !== researchMode

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100">Settings</h1>
      <p className="mt-2 text-sm text-zinc-500">Platform-wide configuration.</p>

      {/* ── Compliance Research Model ── */}
      <div className="mt-8 max-w-xl">
        <h2 className="text-sm font-medium text-zinc-300 mb-1">Compliance Research Model</h2>
        <p className="text-xs text-zinc-500 mb-3">
          Controls which Gemini model is used for jurisdiction &amp; specialization research.
        </p>
        {settings.loading ? (
          <div className="flex items-center gap-2 py-4 text-sm text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading settings...
          </div>
        ) : settings.error ? (
          /* Without this the list renders with no option selected, which reads
             as "no mode is set" rather than "we couldn't find out". */
          <p className="py-4 text-sm text-red-400">{settings.error}</p>
        ) : (
          <div className="space-y-2">
            {RESEARCH_MODELS.map((m) => (
              <Card
                key={m.id}
                className={`flex items-center gap-4 p-4 cursor-pointer transition-colors ${
                  pendingMode === m.id ? 'border-emerald-500 bg-emerald-950/20' : 'hover:border-zinc-700'
                }`}
                onClick={() => setPendingMode(m.id)}
              >
                <div className={`h-3 w-3 rounded-full border-2 shrink-0 ${
                  pendingMode === m.id ? 'border-emerald-500 bg-emerald-500' : 'border-zinc-600'
                }`} />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-100">
                    {m.label} <span className="ml-2 text-xs font-normal text-zinc-500">{m.model}</span>
                  </p>
                  <p className="text-xs text-zinc-500">{m.description}</p>
                </div>
              </Card>
            ))}
          </div>
        )}
        <div className="mt-6">
          <Button onClick={handleSave} disabled={!hasChanges || saving}>
            {saving ? 'Saving...' : hasChanges ? 'Save changes' : 'Saved'}
          </Button>
        </div>
      </div>

      {/* ── Token Quotas ── */}
      <div className="mt-12 max-w-2xl">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-medium text-zinc-300">Token Quotas</h2>
          <div className="flex items-center gap-2">
            <button onClick={() => quotaState.reload()} className="text-zinc-500 hover:text-zinc-300 p-1">
              <RefreshCw size={14} />
            </button>
            <button
              onClick={() => setShowAddQuota(!showAddQuota)}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"
            >
              <Plus size={12} /> Add quota
            </button>
          </div>
        </div>
        <p className="text-xs text-zinc-500 mb-4">
          Control how many AI tokens each user can consume per rolling window. Global defaults apply to all users without a specific quota.
        </p>

        {/* Add quota form */}
        {showAddQuota && (
          <Card className="p-4 mb-4 border-emerald-800/50">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">User email (blank = global)</label>
                <input
                  value={newQuota.user_email}
                  onChange={(e) => setNewQuota({ ...newQuota, user_email: e.target.value })}
                  placeholder="user@example.com"
                  className="w-full text-xs rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-zinc-100 focus:outline-none focus:border-zinc-500"
                />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">Token limit</label>
                <input
                  type="number"
                  value={newQuota.token_limit}
                  onChange={(e) => setNewQuota({ ...newQuota, token_limit: e.target.value })}
                  className="w-full text-xs rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-zinc-100 focus:outline-none focus:border-zinc-500"
                />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">Window (hours)</label>
                <input
                  type="number"
                  value={newQuota.window_hours}
                  onChange={(e) => setNewQuota({ ...newQuota, window_hours: e.target.value })}
                  className="w-full text-xs rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-zinc-100 focus:outline-none focus:border-zinc-500"
                />
              </div>
            </div>
            {quotaError && <p className="text-xs text-red-400 mt-2">{quotaError}</p>}
            <div className="flex gap-2 mt-3">
              <Button onClick={handleAddQuota}>Add</Button>
              <button onClick={() => setShowAddQuota(false)} className="text-xs text-zinc-500">Cancel</button>
            </div>
          </Card>
        )}

        {quotaLoading ? (
          <div className="flex items-center gap-2 py-4 text-sm text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading quotas...
          </div>
        ) : (
          <div className="space-y-2">
            {quotas.map((q) => (
              <Card key={q.id} className="flex items-center gap-4 p-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-100">
                    {q.user_email || q.company_name || 'Global Default'}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {(q.token_limit).toLocaleString()} tokens / {q.window_hours}h
                    {!q.is_active && <span className="ml-2 text-amber-400">(disabled)</span>}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    defaultValue={q.token_limit}
                    onBlur={(e) => {
                      const v = parseInt(e.target.value)
                      if (v && v !== q.token_limit) handleUpdateQuota(q.id, { token_limit: v })
                    }}
                    className="w-24 text-xs rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-100 focus:outline-none focus:border-zinc-500"
                  />
                  <button
                    onClick={() => handleUpdateQuota(q.id, { is_active: !q.is_active })}
                    className={`text-[10px] px-2 py-1 rounded ${q.is_active ? 'text-emerald-400 bg-emerald-900/30' : 'text-zinc-500 bg-zinc-800'}`}
                  >
                    {q.is_active ? 'Active' : 'Off'}
                  </button>
                  <button onClick={() => handleDeleteQuota(q.id)} className="text-zinc-600 hover:text-red-400 p-1">
                    <Trash2 size={12} />
                  </button>
                </div>
              </Card>
            ))}
            {quotas.length === 0 && (
              <p className="text-xs text-zinc-500 py-4">No quotas configured. All users use the hardcoded default (100k tokens / 12h).</p>
            )}
          </div>
        )}
      </div>

      {/* ── Live Token Usage ── */}
      <div className="mt-10 max-w-2xl">
        <h2 className="text-sm font-medium text-zinc-300 mb-1">Live Token Usage (last 12h)</h2>
        <p className="text-xs text-zinc-500 mb-4">Active users and their token consumption in the current window.</p>

        {quotaLoading ? (
          <div className="flex items-center gap-2 py-4 text-sm text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading...
          </div>
        ) : usage.length === 0 ? (
          <p className="text-xs text-zinc-500 py-4">No token usage in the last 12 hours.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-2 font-medium">User</th>
                  <th className="text-left py-2 font-medium">Company</th>
                  <th className="text-right py-2 font-medium">Tokens</th>
                  <th className="text-right py-2 font-medium">Calls</th>
                  <th className="text-right py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {usage.map((u) => {
                  const globalQuota = quotas.find((q) => !q.user_id && !q.company_id)
                  const userQuota = quotas.find((q) => q.user_id === u.user_id)
                  const limit = userQuota?.token_limit ?? globalQuota?.token_limit ?? 100000
                  const pct = Math.round((u.tokens_used / limit) * 100)
                  const over = pct >= 100
                  return (
                    <tr key={u.user_id} className="border-b border-zinc-800/50">
                      <td className="py-2 text-zinc-200">{u.email}</td>
                      <td className="py-2 text-zinc-500">{u.company_name || '—'}</td>
                      <td className="py-2 text-right">
                        <span className={over ? 'text-red-400 font-medium' : 'text-zinc-200'}>
                          {u.tokens_used.toLocaleString()}
                        </span>
                        <span className="text-zinc-600"> / {limit.toLocaleString()}</span>
                        <span className={`ml-1 ${over ? 'text-red-400' : pct >= 80 ? 'text-amber-400' : 'text-zinc-500'}`}>
                          ({pct}%)
                        </span>
                      </td>
                      <td className="py-2 text-right text-zinc-400">{u.call_count}</td>
                      <td className="py-2 text-right text-zinc-400">${Number(u.cost_dollars).toFixed(4)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Beta Invitations ── */}
      <div className="mt-12 max-w-2xl">
        <h2 className="text-sm font-medium text-zinc-300 mb-1">Matcha Work Beta Invitations</h2>
        <p className="text-xs text-zinc-500 mb-4">
          Send private beta invitations for Matcha Work. Recipients get an independent individual account (not attached to any business).
        </p>

        {/* Send form */}
        <Card className="p-4 mb-4">
          <label className="text-[10px] text-zinc-500 mb-1 block">Email addresses (one per line, or comma-separated)</label>
          <textarea
            value={betaEmails}
            onChange={(e) => setBetaEmails(e.target.value)}
            placeholder="jane@example.com&#10;john@example.com"
            rows={3}
            className="w-full text-xs rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-y"
          />
          {betaResult && <p className="text-xs text-emerald-400 mt-2">{betaResult}</p>}
          <div className="mt-3">
            <Button onClick={handleSendBetaInvites} disabled={betaSending || !betaEmails.trim()}>
              <Send size={12} className="mr-1.5" />
              {betaSending ? 'Sending...' : 'Send Invitations'}
            </Button>
          </div>
        </Card>

        {/* Invitation list */}
        {betaLoading ? (
          <div className="flex items-center gap-2 py-4 text-sm text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading invitations...
          </div>
        ) : betaInvites.length === 0 ? (
          <p className="text-xs text-zinc-500 py-4">No invitations sent yet.</p>
        ) : (
          <div className="space-y-1.5">
            {betaInvites.map((inv) => (
              <Card key={inv.id} className="flex items-center gap-3 px-3 py-2.5">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 truncate">{inv.email}</p>
                  <p className="text-[10px] text-zinc-500">
                    Sent {inv.created_at ? new Date(inv.created_at).toLocaleDateString() : '—'}
                    {inv.registered_at && ` · Registered ${new Date(inv.registered_at).toLocaleDateString()}`}
                  </p>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  inv.status === 'registered'
                    ? 'bg-emerald-900/30 text-emerald-400'
                    : inv.status === 'pending'
                    ? 'bg-amber-900/30 text-amber-400'
                    : 'bg-zinc-800 text-zinc-500'
                }`}>
                  {inv.status}
                </span>
                {inv.status === 'pending' && (
                  <button onClick={() => handleRevokeBetaInvite(inv.id)} className="text-zinc-600 hover:text-red-400 p-1">
                    <Trash2 size={12} />
                  </button>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
