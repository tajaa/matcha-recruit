import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Gift, Loader2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeMagazineComp, CappeMagazineReader, CappeMagazineReaders } from '../../types'
import { priceLabel } from '../settings/price'

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '')

const STATE: Record<string, string> = {
  active: 'Paying', trialing: 'Paying', past_due: 'Card failing', unpaid: 'Unpaid', paused: 'Paused', canceled: 'Ended',
}

function readerState(r: CappeMagazineReader): string {
  if (r.status === 'canceled') return 'Ended'
  if (r.cancel_at_period_end && r.current_period_end) return `Ends ${day(r.current_period_end)}`
  return `${STATE[r.status] || r.status}${r.current_period_end ? ` · renews ${day(r.current_period_end)}` : ''}`
}

/** `sites/:siteId/readers` — who pays for the magazine, and who reads it
 *  free on the writer's say-so (comps). A comp opens every paid story to that
 *  email; the reader signs in on the magazine with it. */
export default function Readers() {
  const { siteId } = useParams<{ siteId: string }>()
  const [data, setData] = useState<CappeMagazineReaders | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [months, setMonths] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeMagazineReaders>(`/sites/${siteId}/magazine/readers`)
      .then((d) => { if (live) setData(d) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load your readers') })
    return () => { live = false }
  }, [siteId])

  const give = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      const comp = await cappeApi.post<CappeMagazineComp>(`/sites/${siteId}/magazine/comps`, {
        email: email.trim(), months: months ? Number(months) : null, note: note.trim() || null,
      })
      setData((d) => d && { ...d, comps: [comp, ...d.comps.filter((c) => c.id !== comp.id)] })
      setDone(`${comp.email} can read every story now. We’ve emailed them.`)
      setEmail('')
      setNote('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That didn’t work')
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (comp: CappeMagazineComp) => {
    if (!window.confirm(`Stop ${comp.email}’s free subscription?`)) return
    try {
      await cappeApi.delete(`/sites/${siteId}/magazine/comps/${comp.id}`)
      setData((d) => d && { ...d, comps: d.comps.filter((c) => c.id !== comp.id) })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That didn’t work')
    }
  }

  if (data === null && !error) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  const paying = (data?.subscriptions || []).filter((s) => ['active', 'trialing', 'past_due'].includes(s.status)).length

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className={ui.heading}>Readers</h1>
        <p className={ui.subtitle}>{paying} paying {paying === 1 ? 'reader' : 'readers'}. Readers cancel from their account on your magazine; it ends with the month they paid for.</p>
      </div>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}

      <section className={`${ui.card} p-5`} aria-label="Paid readers">
        <h2 className="mb-3 text-sm font-medium text-zinc-100">Subscriptions</h2>
        {data && data.subscriptions.length === 0 ? (
          <p className="text-sm text-zinc-400">No one has subscribed yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-800">
            {data?.subscriptions.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <span className="min-w-0 truncate text-zinc-100">{r.email || 'A reader who left'}{r.name ? ` · ${r.name}` : ''}</span>
                <span className="text-xs text-zinc-400">{priceLabel(r.total_cents)}/mo · {readerState(r)} · since {day(r.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={`${ui.card} space-y-4 p-5`} aria-label="Free subscriptions">
        <h2 className="text-sm font-medium text-zinc-100">Free subscriptions</h2>
        <form onSubmit={give} className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="reader@example.com"
            className={ui.input} aria-label="Reader’s email" />
          <select value={months} onChange={(e) => setMonths(e.target.value)} className={ui.input} aria-label="For how long">
            <option value="">Until I stop it</option>
            <option value="1">1 month</option>
            <option value="3">3 months</option>
            <option value="6">6 months</option>
            <option value="12">12 months</option>
          </select>
          <button type="submit" disabled={busy || !email.trim()} className={ui.btnPrimary}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Gift className="h-4 w-4" />} Give
          </button>
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="Note to yourself (optional)"
            className={`${ui.input} sm:col-span-3`} aria-label="Note" />
        </form>
        {done && <p className="text-sm text-emerald-400" aria-live="polite">{done}</p>}
        {data && data.comps.length > 0 && (
          <ul className="divide-y divide-zinc-800">
            {data.comps.map((c) => (
              <li key={c.id} className="flex items-center gap-3 py-2.5 text-sm">
                <span className="min-w-0 flex-1 truncate text-zinc-100">{c.email}{c.note ? <span className="text-zinc-500"> · {c.note}</span> : null}</span>
                <span className="text-xs text-zinc-400">{c.expires_at ? `until ${day(c.expires_at)}` : 'no end date'}</span>
                <button type="button" onClick={() => revoke(c)} aria-label={`Stop ${c.email}’s free subscription`}
                  className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><X className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
