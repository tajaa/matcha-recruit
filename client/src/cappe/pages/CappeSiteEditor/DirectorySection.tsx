import { useEffect, useState } from 'react'
import { Loader2, Sparkles, X } from 'lucide-react'
import { cappeApi } from '../../api'
import type { CappeDirectoryListing } from '../../types'

/** Discover listing editor.
 *
 *  Self-contained (owns its own fetch/save keyed on siteId) rather than another
 *  eight fields threaded through useCappeSiteEditor — nothing else on the page
 *  needs this state.
 *
 *  Uses the authed builder's zinc/emerald palette, NOT the landing tokens the
 *  public Discover surface uses: this panel lives inside the app.
 */
export function DirectorySection({ siteId }: { siteId: string }) {
  const [listing, setListing] = useState<CappeDirectoryListing | null>(null)
  const [tagInput, setTagInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [suggesting, setSuggesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    if (!siteId) return
    cappeApi
      .get<CappeDirectoryListing>(`/sites/${siteId}/directory`)
      .then(setListing)
      .catch((e: Error) => { setError(e.message); setLoadFailed(true) })
  }, [siteId])

  // A failed initial load must say so, not just vanish — otherwise a 500 (or a
  // missing site row) reads as "this feature doesn't exist for me" rather than
  // "something broke", and there's nothing on the page to act on.
  if (loadFailed) {
    return (
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">Discover listing</h2>
        <p className="text-sm text-red-400">{error || 'Could not load your Discover listing.'}</p>
      </section>
    )
  }
  if (!listing) return null

  function patch(next: Partial<CappeDirectoryListing>) {
    setListing((prev) => (prev ? { ...prev, ...next } : prev))
    setNotice(null)
  }

  async function save(override?: Partial<CappeDirectoryListing>) {
    if (!listing) return
    const merged = { ...listing, ...override }
    setSaving(true)
    setError(null)
    try {
      const updated = await cappeApi.put<CappeDirectoryListing>(`/sites/${siteId}/directory`, {
        listed: merged.listed,
        category: merged.category,
        tags: merged.tags,
        blurb: merged.blurb,
      })
      setListing(updated)
      setNotice('Listing saved.')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function suggest() {
    setSuggesting(true)
    setError(null)
    try {
      const updated = await cappeApi.post<CappeDirectoryListing>(`/sites/${siteId}/directory/suggest`)
      setListing(updated)
      setNotice('Suggested from your site — edit anything that looks off.')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSuggesting(false)
    }
  }

  // Returns the authoritative tag list (including anything just committed)
  // rather than relying on the caller re-reading `listing` afterward. Blur and
  // click are separate native events, and the button's onClick can fire before
  // React has re-rendered from the input's blur — so `save()` closing over the
  // pre-blur `listing` would silently drop a keyword the user typed but never
  // pressed Enter on. The Save button calls this directly (`addTag()` is
  // idempotent against a duplicate/empty pending value) and passes the result
  // straight into `save({tags: ...})`, sidestepping the stale-closure race
  // entirely instead of depending on event ordering.
  function addTag(): string[] {
    const tag = tagInput.trim().toLowerCase()
    if (!tag || listing!.tags.includes(tag) || listing!.tags.length >= 8) {
      setTagInput('')
      return listing!.tags
    }
    const next = [...listing!.tags, tag]
    patch({ tags: next })
    setTagInput('')
    return next
  }

  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <div className="mb-1 flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold text-zinc-100">Discover listing</h2>
        <button
          type="button"
          onClick={suggest}
          disabled={suggesting}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-60"
        >
          {suggesting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          Suggest for me
        </button>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        How your business appears when people browse Gummfit. Published sites are listed
        automatically.
      </p>

      {/* Say plainly whether anyone can find them, and why not when they can't —
          the directory's quality gate hides a listing with no category or blurb,
          and silently vanishing is the worst version of that. */}
      {listing.blocked ? (
        <p className="mb-4 rounded-lg border border-amber-800/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          This listing is under review and is not currently shown in Discover.
        </p>
      ) : !listing.listed ? (
        <p className="mb-4 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
          Hidden from Discover. People can still reach your site directly.
        </p>
      ) : !listing.visible ? (
        <p className="mb-4 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
          Add a category and a short description to appear in Discover — or publish your
          site if you haven’t yet.
        </p>
      ) : (
        <p className="mb-4 rounded-lg border border-emerald-900/60 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-400">
          Live in Discover.
        </p>
      )}

      <div className="space-y-4">
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={listing.listed}
            onChange={(e) => { patch({ listed: e.target.checked }); void save({ listed: e.target.checked }) }}
            className="mt-0.5 h-4 w-4 rounded border-zinc-700 bg-zinc-950 text-emerald-500"
          />
          <span className="text-sm text-zinc-300">
            List my business in Discover
            <span className="mt-0.5 block text-xs text-zinc-500">
              Free traffic from people searching for what you offer.
            </span>
          </span>
        </label>

        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Category</label>
          <select
            value={listing.category ?? ''}
            onChange={(e) => patch({ category: e.target.value || null })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          >
            <option value="">Choose a category…</option>
            {listing.categories.map((c) => (
              <option key={c.slug} value={c.slug}>{c.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">
            Short description
            <span className="ml-2 text-xs font-normal text-zinc-500">
              {(listing.blurb ?? '').length}/200
            </span>
          </label>
          <textarea
            value={listing.blurb ?? ''}
            onChange={(e) => patch({ blurb: e.target.value.slice(0, 200) })}
            rows={2}
            placeholder="One sentence on what you do — this is your directory card subtitle."
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">
            Search keywords
            <span className="ml-2 text-xs font-normal text-zinc-500">{listing.tags.length}/8</span>
          </label>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {listing.tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs text-zinc-300"
              >
                {tag}
                <button
                  type="button"
                  onClick={() => patch({ tags: listing.tags.filter((t) => t !== tag) })}
                  aria-label={`Remove ${tag}`}
                  className="text-zinc-500 hover:text-zinc-200"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
          <input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag() } }}
            onBlur={addTag}
            disabled={listing.tags.length >= 8}
            placeholder="What would someone type to find you? Press Enter"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
          />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
        {notice && <p className="text-sm text-emerald-400">{notice}</p>}

        <button
          type="button"
          onClick={() => void save({ tags: addTag() })}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
        >
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Save listing
        </button>
      </div>
    </section>
  )
}
