import { useState } from 'react'
import { saveRecapPreferences } from '../../api/matchaWork/recaps'
import { useRecapPreferences } from '../../hooks/useRecapPreferences'
import type { RecapPreferences as Preferences } from '../../types'

export default function RecapPreferences() {
  const initial = useRecapPreferences()
  const [saved, setSaved] = useState<Preferences | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const value = saved ?? initial
  if (!value?.available) return null
  async function update(patch: Partial<Preferences>) {
    if (!value) return
    setBusy(true)
    setError('')
    try { setSaved(await saveRecapPreferences({ enabled: value.enabled, email_enabled: value.email_enabled, ...patch })) }
    catch { setError('Could not save recap preferences. Try again.') }
    finally { setBusy(false) }
  }
  return <section className="rounded-xl border border-w-line bg-w-surface p-5">
    <h2 className="text-sm font-semibold text-w-text">Task recaps</h2>
    <p className="my-3 text-xs leading-5 text-w-dim">Save a short private video of key steps and results from new Espresso tasks. Videos stay for 30 days. Source captures stay for 7 days. Idle time is left out.</p>
    <label className="flex items-center gap-2 text-sm text-w-text"><input type="checkbox" checked={value.enabled} disabled={busy} onChange={(e) => void update({ enabled: e.target.checked })} />Create task recap videos</label>
    <label className="mt-3 flex items-center gap-2 text-sm text-w-text"><input type="checkbox" checked={value.email_enabled} disabled={busy} onChange={(e) => void update({ email_enabled: e.target.checked })} />Email me a recap link when tasks finish</label>
    <p className="mt-3 text-xs text-w-dim">Turning creation off stops unfinished videos. Existing videos can be deleted from Recaps.</p>
    {error && <p role="alert" className="mt-2 text-xs text-amber-500">{error}</p>}
  </section>
}
