import { useEffect, useState } from 'react'
import { CheckCircle2, Loader2, RefreshCw, Unlink } from 'lucide-react'
import { api } from '../../api/client'
import { Modal } from '../ui/Modal'

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
  const [loading, setLoading] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Connect form state
  const [gustoCompanyId, setGustoCompanyId] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
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

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault()
    setConnecting(true)
    setConnectError(null)
    try {
      const result = await api.post<ConnectionStatus>('/provisioning/hris/connect', {
        mode: 'gusto',
        gusto_company_id: gustoCompanyId.trim(),
        client_id: clientId.trim(),
        client_secret: clientSecret,
        test_connection: true,
      })
      setConnectionStatus(result)
      setClientSecret('')
      setClientId('')
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : 'Connection failed')
    } finally {
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
      setGustoCompanyId('')
      setClientId('')
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
    <Modal open={open} onClose={handleClose} title="Sync employees from Gusto" width="sm">
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
        <ConnectForm
          gustoCompanyId={gustoCompanyId}
          clientId={clientId}
          clientSecret={clientSecret}
          connecting={connecting}
          error={connectError}
          onChange={{ gustoCompanyId: setGustoCompanyId, clientId: setClientId, clientSecret: setClientSecret }}
          onSubmit={handleConnect}
        />
      )}
    </Modal>
  )
}

// ---------------------------------------------------------------------------

function ConnectForm({
  gustoCompanyId,
  clientId,
  clientSecret,
  connecting,
  error,
  onChange,
  onSubmit,
}: {
  gustoCompanyId: string
  clientId: string
  clientSecret: string
  connecting: boolean
  error: string | null
  onChange: { gustoCompanyId: (v: string) => void; clientId: (v: string) => void; clientSecret: (v: string) => void }
  onSubmit: (e: React.FormEvent) => void
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-xs text-zinc-400">
        Connect your Gusto account to automatically import employees into Matcha.
        You'll need a Gusto API application with <code className="text-zinc-300">employees:read</code> scope.
      </p>
      <Field label="Gusto company ID" required>
        <input
          type="text"
          required
          value={gustoCompanyId}
          onChange={(e) => onChange.gustoCompanyId(e.target.value)}
          placeholder="e.g. abc12345-…"
          className={inputCls}
        />
      </Field>
      <Field label="Client ID" required>
        <input
          type="text"
          required
          value={clientId}
          onChange={(e) => onChange.clientId(e.target.value)}
          placeholder="Your Gusto OAuth client ID"
          className={inputCls}
        />
      </Field>
      <Field label="Client secret" required>
        <input
          type="password"
          required
          value={clientSecret}
          onChange={(e) => onChange.clientSecret(e.target.value)}
          placeholder="Your Gusto OAuth client secret"
          className={inputCls}
        />
      </Field>
      {error && (
        <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/30 rounded px-3 py-2">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={connecting}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {connecting && <Loader2 className="w-4 h-4 animate-spin" />}
        {connecting ? 'Connecting…' : 'Connect Gusto'}
      </button>
    </form>
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

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-900/15 border border-emerald-800/30">
        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-emerald-300">Connected to Gusto</p>
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

      <div className="flex justify-center pt-1">
        <button
          onClick={onDisconnect}
          disabled={disconnecting}
          className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors flex items-center gap-1"
        >
          <Unlink className="w-3 h-3" />
          {disconnecting ? 'Disconnecting…' : 'Disconnect Gusto'}
        </button>
      </div>
    </div>
  )
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-zinc-400 mb-1.5">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}

const inputCls =
  'w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700 transition-colors'
