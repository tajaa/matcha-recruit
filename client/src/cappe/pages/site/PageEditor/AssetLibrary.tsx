import { useContext, useEffect, useRef, useState } from 'react'
import { Loader2, Sparkles, Trash2, Upload, X } from 'lucide-react'
import { cappeApi } from '../../../api'
import { SiteCtx } from './context'

type Asset = {
  id: string
  kind: 'generated' | 'upload'
  url: string
  prompt: string | null
  aspect: string | null
  image_size: string | null
  created_at: string
}

/** Per-site image asset library — everything a `POST /generate-image` or
 *  `/upload` has ever produced (`cappe_assets`, migration zzzzcappe23).
 *
 *  Two layouts share one fetch/delete implementation:
 *  - `variant="popover"` (default): a small positioned dropdown for the field
 *    editor's Library button. Caller supplies a `relative` parent; this
 *    renders `absolute` inside it and closes on outside click.
 *  - `variant="panel"`: fills its container — Merlin's Assets tab. No
 *    positioning of its own, bigger thumbnails, nothing to click outside of. */
export function AssetLibrary({
  onPick, onClose, variant = 'popover',
}: {
  onPick: (url: string) => void
  onClose: () => void
  variant?: 'popover' | 'panel'
}) {
  const siteId = useContext(SiteCtx)
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [kind, setKind] = useState<'all' | 'generated' | 'upload'>('all')
  const boxRef = useRef<HTMLDivElement>(null)
  const panel = variant === 'panel'

  useEffect(() => {
    if (!siteId) return
    let cancelled = false
    setLoading(true)
    const qs = kind === 'all' ? '' : `?kind=${kind}`
    cappeApi.get<{ assets: Asset[] }>(`/sites/${siteId}/assets${qs}`)
      .then((res) => { if (!cancelled) setAssets(res.assets) })
      .catch(() => { if (!cancelled) setAssets([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [siteId, kind])

  useEffect(() => {
    if (panel) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) onClose()
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [onClose, panel])

  const remove = async (id: string) => {
    setAssets((a) => a.filter((x) => x.id !== id))
    try {
      await cappeApi.delete(`/sites/${siteId}/assets/${id}`)
    } catch {
      // Row-only delete; a stale entry reappearing on next open is the worst
      // case, not a broken page (the blob and any live reference are untouched).
    }
  }

  return (
    <div
      ref={boxRef}
      className={
        panel
          ? 'flex min-h-0 flex-1 flex-col'
          : 'absolute left-0 right-0 z-20 mt-1 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl'
      }
    >
      <div className={`flex items-center justify-between ${panel ? 'px-3 py-2' : 'border-b border-zinc-800 px-2.5 py-1.5'}`}>
        <div className="flex gap-1">
          {(['all', 'generated', 'upload'] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={`rounded px-2 py-1 text-[11px] font-medium capitalize ${kind === k ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}
            >
              {k === 'all' ? 'All' : k}
            </button>
          ))}
        </div>
        {!panel && (
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      <div className={panel ? 'flex-1 overflow-y-auto px-3 pb-3' : 'max-h-56 overflow-y-auto p-2'}>
        {loading && (
          <div className="flex items-center justify-center py-6 text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        )}
        {!loading && assets.length === 0 && (
          <p className="px-1 py-4 text-center text-[11px] text-zinc-500">
            No images yet — generate or upload one and it'll show up here.
          </p>
        )}
        {!loading && assets.length > 0 && (
          <div className={panel ? 'grid grid-cols-3 gap-2' : 'grid grid-cols-4 gap-1.5'}>
            {assets.map((a) => (
              <div key={a.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onPick(a.url)}
                  className="block aspect-square w-full overflow-hidden rounded border border-zinc-800 hover:border-emerald-500"
                  title={a.prompt || a.url}
                >
                  <img src={a.url} alt="" className="h-full w-full object-cover" />
                </button>
                <div className="pointer-events-none absolute left-0.5 top-0.5 rounded bg-black/60 p-0.5 text-white opacity-0 group-hover:opacity-100">
                  {a.kind === 'generated' ? <Sparkles className="h-2.5 w-2.5" /> : <Upload className="h-2.5 w-2.5" />}
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); remove(a.id) }}
                  className="absolute right-0.5 top-0.5 rounded bg-black/60 p-0.5 text-white opacity-0 hover:bg-red-600 group-hover:opacity-100"
                  title="Remove from library"
                >
                  <Trash2 className="h-2.5 w-2.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
