import { useEffect, useState } from 'react'
import { cappeApi } from '../api'
import type { CappeSite } from '../types'

export default function MobileAppSettingsCard({ siteId }: { siteId: string }) {
  const [scheme, setScheme] = useState('')
  const [bundle, setBundle] = useState('')
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let live = true
    cappeApi.get<CappeSite>(`/sites/${siteId}`).then(site => {
      if (!live) return
      setScheme(site.app_url_scheme || ''); setBundle(site.app_bundle_id || ''); setReady(true)
    }).catch(error => { if (live) setMessage(error instanceof Error ? error.message : 'Could not load app settings') })
    return () => { live = false }
  }, [siteId])
  async function save() {
    setSaving(true); setMessage('')
    try {
      await cappeApi.put(`/sites/${siteId}`, { app_url_scheme: scheme.trim() || null, app_bundle_id: bundle.trim() || null })
      setMessage('Saved')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not save') }
    finally { setSaving(false) }
  }
  return <section className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
    <h2 className="mb-3 text-sm font-medium text-zinc-200">Mobile app</h2>
    <div className="flex flex-wrap gap-3 text-sm text-zinc-300">
      <label>Return URL scheme <input aria-label="Return URL scheme" value={scheme} onChange={e => setScheme(e.target.value)} placeholder="ahnimal" className="block rounded bg-zinc-950 p-2" /></label>
      <label>iOS bundle identifier <input aria-label="iOS bundle identifier" value={bundle} onChange={e => setBundle(e.target.value)} placeholder="com.ahnimal.app" className="block rounded bg-zinc-950 p-2" /></label>
      <button onClick={save} disabled={!ready || saving} className="self-end rounded bg-zinc-100 px-3 py-2 text-zinc-900 disabled:opacity-50">{saving ? 'Saving…' : 'Save'}</button>
    </div><p role="status" className="mt-2 text-sm text-zinc-400">{message}</p>
  </section>
}
