import { ImagePlus, X } from 'lucide-react'
import type { CappeAsset } from '../../types'
import { thumbUrl } from '../library/assets'

/** A library picture in a form: its thumbnail (click to change it), its alt
 *  text and credit, and a button to take it out. */
export default function PictureSlot({ assetId, assets, onPick, onClear, label = 'Picture' }: {
  assetId: string | null
  assets: Map<string, CappeAsset>
  onPick: () => void
  onClear: () => void
  label?: string
}) {
  const asset = assetId ? assets.get(assetId) : undefined
  return (
    <div className="flex items-center gap-3">
      <button type="button" onClick={onPick} aria-label={asset ? `Change ${label.toLowerCase()}` : `Choose ${label.toLowerCase()}`}
        className="flex h-16 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-dashed border-zinc-700 bg-zinc-950 hover:border-emerald-500">
        {asset ? <img src={thumbUrl(asset)} alt={asset.alt || ''} className="h-full w-full object-cover" /> : <ImagePlus className="h-5 w-5 text-zinc-500" />}
      </button>
      <div className="min-w-0 flex-1 text-xs text-zinc-500">
        {asset ? (
          <>
            <p className="truncate text-zinc-300">{asset.alt || asset.title || 'No alt text yet'}</p>
            <p className="truncate">{asset.credit_line || (asset.kind === 'upload' ? 'No credit' : '')}</p>
          </>
        ) : <p>{label}: none chosen</p>}
      </div>
      {asset && (
        <button type="button" onClick={onClear} className="text-zinc-500 hover:text-zinc-300" aria-label={`Remove ${label.toLowerCase()}`}>
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
