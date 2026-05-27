import { useEffect, useState } from 'react'
import { CheckCircle2, Loader2, RefreshCw, Unlink, Wallet, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { Modal } from '../ui/Modal'
import { useMe } from '../../hooks/useMe'

type ConnectionStatus = {
  connected: boolean
  status: string
  mode: string | null
  gusto_company_id: string | null
  has_client_secret: boolean
  last_sync_at: string | null
  total_synced_employees: number
  last_error: string | null
}

type SyncResult = {
  sync_run_id: string
  status: string
  created_count: number
  updated_count: number
  skipped_count: number
  error_count: number
  errors: { employee_id?: string; message: string }[]
}

type Props = {
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

export function HRISSyncModal({ open, onClose, onSuccess }: Props) {
  const { hasFeature } = useMe()
  // Legacy hris_import umbrella enables both providers.
  const legacyBoth = hasFeature('hris_import')
  const showGusto = hasFeature('hris_gusto') || legacyBoth
  const showFinch = hasFeature('hris_finch') || legacyBoth

  const [loading, setLoading] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Connect state
  const [connecting, setConnecting] = useState(false)
  const [connectError, setConnectError] = useState<string | null>(null)

  // Sync state
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)

  // Disconnect state
  const [disconnecting, setDisconnecting] = useState(false)

  useEffect(() => {
    if (!open) return
    setConnectionStatus(null)
    setFetchError(null)
    setSyncResult(null)
    setSyncError(null)
    setLoading(true)
    api.get<ConnectionStatus>('/provisioning/hris/status')
      .then(setConnectionStatus)
      .catch((e) => setFetchError(e instanceof Error ? e.message : 'Failed to load status'))
      .finally(() => setLoading(false))
  }, [open])

  async function handleConnect(authorizePath: string) {
    setConnecting(true)
    setConnectError(null)
    try {
      const res = await api.get<{ oauth_url: string }>(authorizePath)
      window.location.href = res.oauth_url
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : 'Connection failed')
      setConnecting(false)
    }
  }

  async function handleSync() {
    setSyncing(true)
    setSyncResult(null)
    setSyncError(null)
    try {
      const result = await api.post<SyncResult>('/provisioning/hris/sync', {})
      setSyncResult(result)
      onSuccess()
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true)
    try {
      await api.post('/provisioning/hris/disconnect', {})
      setConnectionStatus(null)
      setSyncResult(null)
    } catch {
      // disconnect failed — leave state unchanged
    } finally {
      setDisconnecting(false)
    }
  }

  function handleClose() {
    setSyncResult(null)
    setSyncError(null)
    setConnectError(null)
    onClose()
  }

  const isConnected = connectionStatus?.connected === true

  return (
    <Modal open={open} onClose={handleClose} title="Sync employees from HRIS" width="sm">
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
        </div>
      ) : fetchError ? (
        <p className="text-xs text-red-400 py-4">{fetchError}</p>
      ) : isConnected ? (
        <ConnectedPanel
          status={connectionStatus!}
          syncing={syncing}
          syncResult={syncResult}
          syncError={syncError}
          disconnecting={disconnecting}
          onSync={handleSync}
          onDisconnect={handleDisconnect}
        />
      ) : (
        <ConnectProviders
          connecting={connecting}
          error={connectError}
          showGusto={showGusto}
          showFinch={showFinch}
          onConnectGusto={() => handleConnect('/provisioning/hris/authorize')}
          onConnectFinch={() => handleConnect('/provisioning/hris/finch/authorize')}
        />
      )}
    </Modal>
  )
}

// ---------------------------------------------------------------------------

function ConnectProviders({
  connecting,
  error,
  showGusto,
  showFinch,
  onConnectGusto,
  onConnectFinch,
}: {
  connecting: boolean
  error: string | null
  showGusto: boolean
  showFinch: boolean
  onConnectGusto: () => void
  onConnectFinch: () => void
}) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-zinc-400">
        Connect your payroll or HRIS to import employees. You'll be redirected to
        log in and approve access.
      </p>
      {error && (
        <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/30 rounded px-3 py-2">
          {error}
        </p>
      )}
      {showGusto && (
        <button
          onClick={onConnectGusto}
          disabled={connecting}
          className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          {connecting && <Loader2 className="w-4 h-4 animate-spin" />}
          {connecting ? 'Redirecting…' : 'Connect with Gusto'}
        </button>
      )}
      {showFinch && (
        <button
          onClick={onConnectFinch}
          disabled={connecting}
          className="w-full bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed text-zinc-100 text-sm font-medium py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          {connecting && <Loader2 className="w-4 h-4 animate-spin" />}
          {connecting ? 'Redirecting…' : 'Connect another HRIS (via Finch)'}
        </button>
      )}
      {showFinch && (
        <p className="text-[11px] text-zinc-600">
          Finch supports ADP, Paychex, Workday, Rippling, and 200+ other providers.
        </p>
      )}
    </div>
  )
}

function ConnectedPanel({
  status,
  syncing,
  syncResult,
  syncError,
  disconnecting,
  onSync,
  onDisconnect,
}: {
  status: ConnectionStatus
  syncing: boolean
  syncResult: SyncResult | null
  syncError: string | null
  disconnecting: boolean
  onSync: () => void
  onDisconnect: () => void
}) {
  const lastSync = status.last_sync_at
    ? new Date(status.last_sync_at).toLocaleString()
    : null

  const providerLabel = status.mode === 'finch' ? 'Finch' : 'Gusto'

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-900/15 border border-emerald-800/30">
        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-emerald-300">Connected to {providerLabel}</p>
          {status.gusto_company_id && (
            <p className="text-[11px] text-zinc-500 truncate">Company: {status.gusto_company_id}</p>
          )}
        </div>
      </div>

      {lastSync && (
        <div className="text-xs text-zinc-500">
          Last sync: <span className="text-zinc-400">{lastSync}</span>
          {status.total_synced_employees > 0 && (
            <> &middot; <span className="text-zinc-400">{status.total_synced_employees} employees</span></>
          )}
        </div>
      )}

      {syncResult && (
        <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 px-3 py-2.5 space-y-1">
          <p className="text-xs font-medium text-zinc-200">Sync complete</p>
          <div className="flex gap-3 text-[11px]">
            <span className="text-emerald-400">+{syncResult.created_count} added</span>
            <span className="text-blue-400">{syncResult.updated_count} updated</span>
            <span className="text-zinc-500">{syncResult.skipped_count} skipped</span>
            {syncResult.error_count > 0 && (
              <span className="text-red-400">{syncResult.error_count} errors</span>
            )}
          </div>
          {syncResult.errors.length > 0 && (
            <ul className="text-[11px] text-red-400 mt-1 space-y-0.5">
              {syncResult.errors.slice(0, 3).map((err, i) => (
                <li key={i} className="truncate">{err.message}</li>
              ))}
              {syncResult.errors.length > 3 && (
                <li className="text-zinc-500">+{syncResult.errors.length - 3} more</li>
              )}
            </ul>
          )}
        </div>
      )}

      {syncError && (
        <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/30 rounded px-3 py-2">
          {syncError}
        </p>
      )}

      <button
        onClick={onSync}
        disabled={syncing}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
        {syncing ? 'Syncing…' : 'Sync now'}
      </button>

      <BenefitsManager mode={status.mode} />

      <div className="flex justify-center pt-1">
        <button
          onClick={onDisconnect}
          disabled={disconnecting}
          className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors flex items-center gap-1"
        >
          <Unlink className="w-3 h-3" />
          {disconnecting ? 'Disconnecting…' : `Disconnect ${providerLabel}`}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

type BenefitMeta = { type: string; description: string; frequencies?: string[] }
type Benefit = { benefit_id: string; type: string; description: string; frequency?: string }

/**
 * Create + list company benefits/deductions, written to the payroll provider
 * via Finch's Deductions API. Only shown for Finch connections on companies with
 * the `hris_deductions` feature — and only QuickBooks/Gusto/ADP-class providers
 * actually support it (others surface a "not supported" notice from /meta).
 */
function BenefitsManager({ mode }: { mode: string | null }) {
  const { hasFeature } = useMe()
  const enabled = mode === 'finch' && hasFeature('hris_deductions')

  const [loading, setLoading] = useState(false)
  const [meta, setMeta] = useState<BenefitMeta[]>([])
  const [benefits, setBenefits] = useState<Benefit[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [type, setType] = useState('')
  const [description, setDescription] = useState('')
  const [frequency, setFrequency] = useState('every_paycheck')
  const [creating, setCreating] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    setLoading(true)
    setLoadError(null)
    Promise.allSettled([
      api.get<BenefitMeta[]>('/provisioning/hris/benefits/meta'),
      api.get<Benefit[]>('/provisioning/hris/benefits'),
    ]).then(([m, b]) => {
      if (m.status === 'fulfilled') {
        setMeta(m.value)
        const first = m.value[0]
        if (first) {
          setType(first.type)
          setFrequency(first.frequencies?.[0] ?? 'every_paycheck')
        }
      } else {
        setLoadError(
          m.reason instanceof Error ? m.reason.message : 'Benefits not supported for this provider',
        )
      }
      if (b.status === 'fulfilled') setBenefits(b.value)
    }).finally(() => setLoading(false))
  }, [enabled])

  const selectedMeta = meta.find((m) => m.type === type)
  const freqs = selectedMeta?.frequencies?.length ? selectedMeta.frequencies : ['every_paycheck']

  async function create() {
    if (!type || !description.trim()) return
    setCreating(true)
    setMsg(null)
    try {
      await api.post('/provisioning/hris/benefits', {
        type,
        description: description.trim(),
        frequency,
      })
      setDescription('')
      setMsg('Created — written to provider via Finch.')
      // Benefit is readable immediately even while the async job settles.
      const list = await api.get<Benefit[]>('/provisioning/hris/benefits')
      setBenefits(list)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Create failed')
    } finally {
      setCreating(false)
    }
  }

  if (!enabled) return null

  return (
    <div className="border-t border-zinc-800 pt-4 space-y-3">
      <div className="flex items-center gap-2">
        <Wallet className="w-4 h-4 text-zinc-500" />
        <span className="text-xs font-medium text-zinc-300">Benefits &amp; deductions</span>
      </div>

      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
      ) : loadError ? (
        <p className="text-[11px] text-amber-400 bg-amber-950/20 border border-amber-900/30 rounded px-3 py-2">
          {loadError}
        </p>
      ) : (
        <>
          {benefits.length > 0 && (
            <ul className="space-y-1">
              {benefits.map((b) => (
                <li key={b.benefit_id} className="text-[11px] text-zinc-400 flex justify-between gap-2">
                  <span className="truncate">{b.description}</span>
                  <span className="text-zinc-600 font-mono shrink-0">{b.type}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="space-y-2">
            <select
              value={type}
              onChange={(e) => {
                setType(e.target.value)
                const m = meta.find((x) => x.type === e.target.value)
                setFrequency(m?.frequencies?.[0] ?? 'every_paycheck')
              }}
              className="w-full bg-zinc-900 border border-zinc-700 rounded text-xs text-zinc-200 px-2 py-1.5"
            >
              {meta.map((m) => (
                <option key={m.type} value={m.type}>{m.description} ({m.type})</option>
              ))}
            </select>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description (e.g. Company 401(k))"
              className="w-full bg-zinc-900 border border-zinc-700 rounded text-xs text-zinc-200 px-2 py-1.5"
            />
            {freqs.length > 1 && (
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 rounded text-xs text-zinc-200 px-2 py-1.5"
              >
                {freqs.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            )}
            <button
              onClick={create}
              disabled={creating || !description.trim()}
              className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium py-2 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              {creating ? 'Creating…' : 'Create benefit'}
            </button>
            {msg && <p className="text-[11px] text-zinc-400">{msg}</p>}
            <p className="text-[10px] text-zinc-600">
              Written to the payroll provider via Finch. Async — provider-side confirmation may lag.
            </p>
          </div>
        </>
      )}
    </div>
  )
}

