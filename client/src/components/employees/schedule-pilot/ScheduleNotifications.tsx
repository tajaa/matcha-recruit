import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Loader2 } from 'lucide-react'
import { authorizeSalesSquare, fetchSalesSetup, registerSalesSender } from '../../../api/employees/scheduleSales'
import type { SalesSetupStatus } from '../../../types/scheduleSales'

const button = 'rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-200 hover:border-emerald-500/50 disabled:opacity-40'
const input = 'mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100'

export default function ScheduleNotifications({
  locationId, locationName, canManage, salesEnabled, hasProposal, onOpenReview,
}: {
  locationId: string
  locationName: string
  canManage: boolean
  salesEnabled: boolean
  hasProposal: boolean
  onOpenReview(): void
}) {
  const [loaded, setLoaded] = useState<{ locationId: string; status?: SalesSetupStatus; error?: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [email, setEmail] = useState('')
  const [subject, setSubject] = useState('')
  const [busy, setBusy] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const eligible = canManage && salesEnabled
  const current = loaded?.locationId === locationId ? loaded : null
  const status = current?.status

  useEffect(() => {
    if (!eligible) return
    let active = true
    fetchSalesSetup(locationId).then(
      (value) => { if (active) setLoaded({ locationId, status: value }) },
      () => { if (active) setLoaded({ locationId, error: 'Sales setup could not be checked. Retry before assuming a connection is ready.' }) },
    )
    return () => { active = false }
  }, [locationId, eligible, attempt])

  async function register(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setSaveError(null)
    try {
      await registerSalesSender(locationId, email, subject)
      setEmail('')
      setSubject('')
      setAttempt((value) => value + 1)
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : 'Could not register that sales sender.')
    } finally { setBusy(false) }
  }

  async function connect() {
    setBusy(true)
    setSaveError(null)
    try { window.location.assign((await authorizeSalesSquare()).oauth_url) }
    catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : 'Could not start Square setup.')
      setBusy(false)
    }
  }

  const inventoryUrl = `/ops/inventory?setup=sales&location=${encodeURIComponent(locationId)}`
  return (
    <section aria-label="Schedule notifications" className="h-full space-y-5 overflow-y-auto p-4 md:p-6">
      <header>
        <h2 className="flex items-center gap-2 text-base font-medium"><Bell className="h-4 w-4" /> Notifications & setup</h2>
        <p className="mt-1 text-xs text-zinc-400">{locationName} · Sales connections and schedule next steps</p>
      </header>
      <div className="space-y-2 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.05] p-4">
        <h3 className="text-sm font-medium text-emerald-200">{hasProposal ? 'A schedule proposal is ready to review' : 'How generated schedules reach the board'}</h3>
        <p className="text-xs leading-5 text-zinc-300">Generating a schedule prepares a proposal. Review and confirm it to create draft shifts on the board, then publish when you are ready.</p>
        {hasProposal && <button type="button" className={button} onClick={onOpenReview}>Review schedule proposal</button>}
      </div>
      {!canManage ? (
        <p className="text-sm text-zinc-300">A company admin can connect the POS or register a nightly sales email for this store.</p>
      ) : !salesEnabled ? (
        <p className="text-sm leading-6 text-amber-200">Sales intake is not enabled for this account. Ask your Matcha administrator to enable it before connecting a POS or nightly sales email. Scheduling can continue with the saved coverage rules.</p>
      ) : !current ? (
        <p role="status" className="flex items-center gap-2 text-xs text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" /> Checking sales setup…</p>
      ) : current.error ? (
        <div role="alert" className="space-y-2 text-sm text-amber-200"><p>{current.error}</p><button type="button" className={button} onClick={() => setAttempt((value) => value + 1)}>Retry sales check</button></div>
      ) : status && (
        <>
          <div role="status" className={`rounded-xl border p-4 ${status.days_with_sales ? 'border-emerald-500/25' : 'border-amber-500/30 bg-amber-500/[0.05]'}`}>
            <h3 className="text-sm font-medium">{status.days_with_sales ? 'Daily sales have been received' : 'Sales data is not available yet'}</h3>
            <p className="mt-1 text-xs leading-5 text-zinc-300">{status.days_with_sales
              ? `${status.days_with_sales} days of sales in the last eight weeks. Latest business date: ${status.latest_sales_date}.`
              : 'Connect Square or arrange nightly sales exports by email, then receive sales for this store before using sales-based forecasts. You can also import a sales file. Chat messages alone do not import sales; scheduling can still use saved coverage rules.'}</p>
            {status.draft_imports > 0 && <p className="mt-2 text-xs text-amber-200">{status.draft_imports} sales import(s) need mapping or review. <Link to={inventoryUrl} className="underline">Review sales imports</Link></p>}
          </div>
          <div className="space-y-3 rounded-xl border border-zinc-800 p-4">
            <h3 className="text-sm font-medium">Connect your POS</h3>
            <p className="text-xs leading-5 text-zinc-400">Square is supported here. Finch imports payroll and employee records; it does not connect sales in Matcha.</p>
            <p className="text-xs text-zinc-300">{status.square_bound ? 'Square is connected and this store is linked.' : status.square_connected ? 'Square is connected. Link this store before sales can arrive.' : 'Square is not connected.'}</p>
            {!status.square_configured && <p className="text-xs text-amber-200">A Matcha administrator must configure Square before a new connection can be started.</p>}
            {!status.square_sync_enabled && <p className="text-xs text-amber-200">Automatic Square sync is paused. A Matcha administrator must enable it; you can run a manual sync from Square setup.</p>}
            <div className="flex flex-wrap gap-2">
              {!status.square_connected && <button type="button" className={button} disabled={busy || !status.square_configured} onClick={() => void connect()}>Connect Square</button>}
              <Link to={inventoryUrl} className={button}>Open Square setup & sales imports</Link>
            </div>
            <p className="text-[11px] leading-5 text-zinc-500">Link the Square store, map sold items and sync finalized sales. Connecting alone does not import history.</p>
          </div>
          <div className="space-y-3 rounded-xl border border-zinc-800 p-4">
            <h3 className="text-sm font-medium">Nightly sales email</h3>
            <p className="text-xs leading-5 text-zinc-400">Schedule an itemized daily sales export from your POS, with a business date and sales amounts. Use a distinct sender for each store.</p>
            {status.mailbox_configured && status.mailbox_address && status.email_poll_enabled
              ? <p className="text-xs text-zinc-300">Send the nightly report to <strong>{status.mailbox_address}</strong>.</p>
              : <p className="text-xs text-amber-200">Nightly email intake is not ready. A Matcha administrator must configure the intake mailbox, provide its receiving address and enable processing. Registering a sender alone does not activate it.</p>}
            {status.email_registered && <p className="text-xs text-emerald-200">A sales sender is registered for this store.</p>}
            <form onSubmit={(event) => void register(event)} className="space-y-3">
              <label className="block text-xs text-zinc-400">POS report sender email<input required type="email" maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} className={input} /></label>
              <label className="block text-xs text-zinc-400">Subject must contain (optional)<input maxLength={200} value={subject} onChange={(event) => setSubject(event.target.value)} className={input} /></label>
              <button type="submit" className={button} disabled={busy || !email.trim()}>{busy ? 'Saving…' : 'Register sales sender'}</button>
            </form>
            <p className="text-[11px] leading-5 text-zinc-500">Unmapped email imports wait for review. An unknown sender is never imported automatically.</p>
          </div>
          <button type="button" className={button} onClick={() => setAttempt((value) => value + 1)}>Recheck sales setup</button>
        </>
      )}
      {saveError && <p role="alert" className="text-xs text-red-300">{saveError}</p>}
    </section>
  )
}
