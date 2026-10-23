import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ExternalLink, Globe, ImagePlus, Loader2, Search, Sparkles, Trash2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeAsset, CappeAssetKind, CappeStockSource } from '../../types'
import { creditEditable, thumbUrl } from './assets'
import IllustrateForm from './IllustrateForm'
import StockSearch from './StockSearch'

const KINDS: { key: '' | CappeAssetKind; label: string }[] = [
  { key: '', label: 'All' },
  { key: 'upload', label: 'Uploads' },
  { key: 'stock', label: 'Archive' },
  { key: 'generated', label: 'AI' },
  { key: 'edit', label: 'Edited' },
]

/**
 * A site's picture library — uploads, archive imports and AI images — with
 * what a story prints beside each one: alt text, caption and credit.
 *
 * `onPick` turns it into a picker (the story editor uses it, passing its
 * `postId`); without it the panel is the Library page. "Find free photos"
 * imports archive pictures into the same list (`stockQuery` opens it on a
 * search), and "Illustrate" adds a labeled AI illustration.
 */
export default function LibraryPanel({ siteId, onPick, postId, stockQuery }: {
  siteId: string
  onPick?: (asset: CappeAsset) => void
  postId?: string
  stockQuery?: { source: CappeStockSource; query: string }
}) {
  const [assets, setAssets] = useState<CappeAsset[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [kind, setKind] = useState<'' | CappeAssetKind>('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [open, setOpen] = useState<'' | 'upload' | 'find' | 'illustrate'>(stockQuery ? 'find' : '')
  const toggle = (what: typeof open) => setOpen((now) => (now === what ? '' : what))
  const generation = useRef(0)

  // Typing settles for a moment before the list is asked again.
  useEffect(() => {
    const t = setTimeout(() => setSearch(query.trim()), 300)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => {
    const gen = ++generation.current
    const params = new URLSearchParams()
    if (kind) params.set('kind', kind)
    if (search) params.set('q', search)
    const qs = params.toString()
    cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${siteId}/assets${qs ? `?${qs}` : ''}`)
      .then((res) => { if (gen === generation.current) { setAssets(res.assets); setLoadError(null) } })
      .catch((e) => {
        if (gen === generation.current) setLoadError(e instanceof Error ? e.message : 'Failed to load your pictures')
      })
  }, [siteId, kind, search])

  const selected = assets?.find((a) => a.id === selectedId) || null

  const replace = (asset: CappeAsset) =>
    setAssets((list) => (list ? list.map((a) => (a.id === asset.id ? asset : a)) : list))

  const added = (asset: CappeAsset) => {
    setAssets((list) => [asset, ...(list || [])])
    setSelectedId(asset.id)
    setOpen('')
  }

  // An archive import lands at the top without taking over the details pane.
  const imported = useCallback((asset: CappeAsset) => {
    setAssets((list) => [asset, ...(list || []).filter((a) => a.id !== asset.id)])
  }, [])

  const removed = (id: string) => {
    setAssets((list) => (list ? list.filter((a) => a.id !== id) : list))
    setSelectedId(null)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1" role="tablist" aria-label="Kind of picture">
          {KINDS.map((k) => (
            <button
              key={k.key || 'all'}
              type="button"
              role="tab"
              aria-selected={kind === k.key}
              onClick={() => setKind(k.key)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${kind === k.key ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <label className="relative ml-auto min-w-[12rem] flex-1 sm:max-w-xs">
          <span className="sr-only">Search your pictures</span>
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search alt text, captions, credits"
            className={`${ui.input} pl-9`}
          />
        </label>
        <button type="button" className={ui.btnGhost} aria-expanded={open === 'find'} onClick={() => toggle('find')}>
          <Globe className="h-4 w-4" /> Find free photos
        </button>
        <button type="button" className={ui.btnGhost} aria-expanded={open === 'illustrate'} onClick={() => toggle('illustrate')}>
          <Sparkles className="h-4 w-4" /> Illustrate
        </button>
        <button type="button" className={ui.btnPrimary} onClick={() => toggle('upload')}>
          <ImagePlus className="h-4 w-4" /> Upload a picture
        </button>
      </div>

      {open === 'upload' && <UploadForm siteId={siteId} onDone={added} onCancel={() => setOpen('')} />}
      {open === 'find' && <StockSearch siteId={siteId} postId={postId} onImported={imported} initial={stockQuery} />}
      {open === 'illustrate' && <IllustrateForm siteId={siteId} onDone={added} onCancel={() => setOpen('')} />}

      {loadError && <p role="alert" className="text-sm text-red-400">{loadError}</p>}

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div>
          {assets === null && !loadError && (
            <div className="flex justify-center py-12 text-zinc-500"><Loader2 className="h-5 w-5 animate-spin" /></div>
          )}
          {assets && assets.length === 0 && (
            <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-center text-sm text-zinc-500">
              {search || kind ? 'Nothing matches.' : 'No pictures yet. Add your own photos to start a story.'}
            </p>
          )}
          {assets && assets.length > 0 && (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {assets.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(a.id)}
                    aria-pressed={a.id === selectedId}
                    className={`group block w-full overflow-hidden rounded-lg border text-left ${a.id === selectedId ? 'border-emerald-500' : 'border-zinc-800 hover:border-zinc-600'}`}
                  >
                    <span className="relative block aspect-[4/3] bg-zinc-900">
                      <img src={thumbUrl(a)} alt={a.alt || ''} loading="lazy" className="h-full w-full object-cover" />
                      {a.ai_generated && (
                        <span className="absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                          <Sparkles className="h-3 w-3" /> AI
                        </span>
                      )}
                    </span>
                    <span className="block truncate px-2 py-1.5 text-[11px] text-zinc-400">
                      {a.credit_line || a.alt || (a.kind === 'upload' ? 'No credit yet' : '')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {selected && (
          <AssetDetails
            key={selected.id}
            siteId={siteId}
            asset={selected}
            onSaved={replace}
            onRemoved={removed}
            onClose={() => setSelectedId(null)}
            onPick={onPick}
          />
        )}
      </div>
    </div>
  )
}

/** Upload one picture with its alt text, caption, credit and the owner's word
 *  that they may publish it. Two columns when it has the room. */
export function UploadForm({ siteId, onDone, onCancel }: {
  siteId: string
  onDone: (asset: CappeAsset) => void
  onCancel: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [alt, setAlt] = useState('')
  const [caption, setCaption] = useState('')
  const [credit, setCredit] = useState('')
  const [aiMade, setAiMade] = useState(false)
  const [rights, setRights] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file || !rights) return
    setBusy(true)
    setError(null)
    const form = new FormData()
    form.append('file', file)
    form.append('rights_attested', 'true')
    form.append('ai_made', aiMade ? 'true' : 'false')
    if (alt.trim()) form.append('alt', alt.trim())
    if (caption.trim()) form.append('caption', caption.trim())
    if (!aiMade && credit.trim()) form.append('credit_line', credit.trim())
    try {
      onDone(await cappeApi.upload<CappeAsset>(`/sites/${siteId}/assets/upload`, form))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className={`${ui.card} @container p-4`} aria-label="Upload a picture">
      <div className="grid gap-3 @md:grid-cols-2">
        <label className="@md:col-span-2">
          <span className={ui.label}>Picture</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-zinc-300 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-sm file:text-zinc-200"
          />
          <span className="mt-1 block text-xs text-zinc-500">
            Up to 15 MB. We remove the location and camera details before it's stored.
          </span>
        </label>
        <label>
          <span className={ui.label}>Alt text</span>
          <input value={alt} onChange={(e) => setAlt(e.target.value)} maxLength={500} className={ui.input}
            placeholder="What's in the picture, for people who can't see it" />
        </label>
        <label>
          <span className={ui.label}>Credit</span>
          <input value={aiMade ? 'AI illustration' : credit} onChange={(e) => setCredit(e.target.value)}
            disabled={aiMade} maxLength={500} className={`${ui.input} disabled:opacity-60`} placeholder="Photo: your name" />
        </label>
        <label className="@md:col-span-2">
          <span className={ui.label}>Caption</span>
          <input value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={1000} className={ui.input} />
        </label>
        <label className="flex items-start gap-2 text-sm text-zinc-300 @md:col-span-2">
          <input type="checkbox" checked={aiMade} onChange={(e) => setAiMade(e.target.checked)} className="mt-0.5" />
          This picture was made with AI. It will always be credited "AI illustration".
        </label>
        <label className="flex items-start gap-2 text-sm text-zinc-300 @md:col-span-2">
          <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} className="mt-0.5" />
          I took this picture or have permission to publish it.
        </label>
        {error && <p role="alert" className="text-sm text-red-400 @md:col-span-2">{error}</p>}
        <div className="flex gap-2 @md:col-span-2">
          <button type="submit" className={ui.btnPrimary} disabled={!file || !rights || busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Add to library
          </button>
          <button type="button" className={ui.btnGhost} onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </form>
  )
}

function AssetDetails({ siteId, asset, onSaved, onRemoved, onClose, onPick }: {
  siteId: string
  asset: CappeAsset
  onSaved: (asset: CappeAsset) => void
  onRemoved: (id: string) => void
  onClose: () => void
  onPick?: (asset: CappeAsset) => void
}) {
  const [alt, setAlt] = useState(asset.alt || '')
  const [caption, setCaption] = useState(asset.caption || '')
  const [credit, setCredit] = useState(asset.credit_line || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const editable = creditEditable(asset)
  const dirty = alt !== (asset.alt || '') || caption !== (asset.caption || '')
    || (editable && credit !== (asset.credit_line || ''))

  const save = async () => {
    setBusy(true)
    setError(null)
    const body: Record<string, string> = { alt, caption }
    if (editable) body.credit_line = credit
    try {
      onSaved(await cappeApi.patch<CappeAsset>(`/sites/${siteId}/assets/${asset.id}`, body))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('Remove this picture from your library? Pages already using it keep it.')) return
    setBusy(true)
    try {
      await cappeApi.delete(`/sites/${siteId}/assets/${asset.id}`)
      onRemoved(asset.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove it')
      setBusy(false)
    }
  }

  return (
    <aside className={`${ui.card} flex flex-col gap-3 self-start p-4`} aria-label="Picture details">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-zinc-100">
          {asset.width && asset.height ? `${asset.width} × ${asset.height}` : 'Picture'}
        </p>
        <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>
      <img src={asset.url} alt={asset.alt || ''} className="max-h-56 w-full rounded-lg object-contain bg-zinc-950" />
      <label>
        <span className={ui.label}>Alt text</span>
        <textarea value={alt} onChange={(e) => setAlt(e.target.value)} maxLength={500} rows={2} className={ui.input} />
      </label>
      <label>
        <span className={ui.label}>Caption</span>
        <textarea value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={1000} rows={2} className={ui.input} />
      </label>
      {editable ? (
        <label>
          <span className={ui.label}>Credit</span>
          <input value={credit} onChange={(e) => setCredit(e.target.value)} maxLength={500} className={ui.input}
            placeholder="Photo: your name" />
        </label>
      ) : (
        <div>
          <span className={ui.label}>Credit</span>
          <p className="text-sm text-zinc-300">{asset.credit_line || '—'}</p>
          <p className="mt-1 text-xs text-zinc-500">
            {asset.ai_generated
              ? 'AI pictures are always credited as AI.'
              : 'This credit comes from the picture\'s license and is printed as is.'}
          </p>
          {asset.source_url && (
            <a href={asset.source_url} target="_blank" rel="noreferrer noopener"
              className={`mt-1 inline-flex items-center gap-1 text-xs ${ui.accentText}`}>
              Where it came from <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      )}
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.btnPrimary} disabled={!dirty || busy} onClick={save}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
        {onPick && (
          <button type="button" className={ui.btnGhost} onClick={() => onPick(asset)}>Use this picture</button>
        )}
        <button type="button" className={`${ui.btnGhost} ml-auto`} onClick={remove} disabled={busy} aria-label="Remove from library">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </aside>
  )
}
