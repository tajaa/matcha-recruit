import { useEffect, useState } from 'react'
import { Loader2, Check, ScrollText, ExternalLink } from 'lucide-react'
import { cappeApi } from '../api'
import { cappeSiteHost } from '../host'
import type { CappePolicies, CappePolicy, CappeSite } from '../types'

// The store's refund, shipping, terms and privacy pages (server:
// services/policies.py). Each is plain text, linked from the store's footer,
// the bag and Stripe's payment page; an empty one isn't published. A store
// selling physical goods can't go live without the refund and shipping ones.
// We offer a starting text for each — it's a prompt to edit, not legal advice.

export default function PoliciesCard({ siteId }: { siteId: string }) {
  const [policies, setPolicies] = useState<CappePolicy[] | null>(null)
  // Where a published policy can be opened: the live store, once it is live.
  const [siteOrigin, setSiteOrigin] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [open, setOpen] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    Promise.all([
      cappeApi.get<CappePolicies>(`/sites/${siteId}/policies`),
      cappeApi.get<CappeSite>(`/sites/${siteId}`),
    ]).then(([r, site]) => {
      setPolicies(r.policies)
      setDrafts(Object.fromEntries(r.policies.map((p) => [p.kind, p.body || ''])))
      setSiteOrigin(site.status === 'published' ? `https://${cappeSiteHost(site)}` : null)
    }).catch((e) => setLoadError(e instanceof Error ? e.message : 'Could not load your policies'))
  }, [siteId, attempt])

  async function save(kind: string, body: string) {
    setError(null); setSaved(null); setSaving(kind)
    try {
      const r = await cappeApi.put<CappePolicies>(`/sites/${siteId}/policies/${kind}`, { body })
      setPolicies(r.policies)
      setDrafts((d) => ({ ...d, [kind]: r.policies.find((p) => p.kind === kind)?.body || '' }))
      setSaved(kind)
      setTimeout(() => setSaved(null), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(null)
    }
  }

  if (loadError) {
    return (
      <div role="alert" className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
        Couldn’t load your policies. {loadError}
        <button onClick={() => { setLoadError(null); setAttempt((n) => n + 1) }} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
      </div>
    )
  }
  if (!policies) return null

  return (
    <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <ScrollText className="h-4 w-4 text-lime-400" /> Store policies
      </div>
      <p className="mb-3 text-xs text-zinc-500">
        Linked from your store’s footer and at checkout. Selling physical products? You need a refund and a shipping
        policy before you can publish. Our starting text is a prompt to edit, not legal advice.
      </p>
      <ul className="divide-y divide-zinc-800">
        {policies.map((p) => {
          const draft = drafts[p.kind] ?? ''
          const changed = draft.trim() !== (p.body || '').trim()
          return (
            <li key={p.kind} className="py-2">
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={() => setOpen(open === p.kind ? null : p.kind)} aria-expanded={open === p.kind}
                  className="text-sm text-zinc-200 hover:text-white">{p.title}</button>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${p.body ? 'bg-lime-500/15 text-lime-300' : 'bg-zinc-800 text-zinc-400'}`}>
                  {p.body ? 'published' : 'not published'}
                </span>
                {p.body && siteOrigin && (
                  <a href={`${siteOrigin}${p.path}`} target="_blank" rel="noopener noreferrer" aria-label={`View your ${p.title.toLowerCase()}`}
                    className="text-zinc-500 hover:text-zinc-200"><ExternalLink className="h-3.5 w-3.5" /></a>
                )}
                {saved === p.kind && <span className="text-xs text-lime-400">Saved</span>}
              </div>
              {open === p.kind && (
                <div className="mt-2 space-y-2">
                  <textarea value={draft} onChange={(e) => setDrafts((d) => ({ ...d, [p.kind]: e.target.value }))}
                    rows={10} maxLength={20000} aria-label={p.title}
                    placeholder="Write it, or start from ours."
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500" />
                  <p className="text-[11px] text-zinc-500">A blank line starts a new paragraph; a short first line reads as its heading.</p>
                  <div className="flex flex-wrap items-center gap-3">
                    <button type="button" disabled={saving === p.kind || !draft.trim() || !changed} onClick={() => save(p.kind, draft)}
                      className="flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-white disabled:opacity-50">
                      {saving === p.kind ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {p.body ? 'Save' : 'Publish'}
                    </button>
                    {!draft.trim() && (
                      <button type="button" onClick={() => setDrafts((d) => ({ ...d, [p.kind]: p.starter }))}
                        className="text-xs font-medium text-lime-400 hover:text-lime-300">Start from our text</button>
                    )}
                    {p.body && (
                      <button type="button" disabled={saving === p.kind}
                        onClick={() => { if (window.confirm(`Take down your ${p.title.toLowerCase()}? Its page and links go away.`)) void save(p.kind, '') }}
                        className="text-xs text-zinc-500 hover:text-red-300">Take down</button>
                    )}
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {error && <p role="alert" className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  )
}
