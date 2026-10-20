import { useState } from 'react'
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import ImageUpload from './ImageUpload'

export type ImageRow = { url: string; alt: string }

export const MAX_IMAGES = 20

const input = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500'

// A product's pictures in order. The first is the cover — the one shown on the
// shop grid, in link previews and in both apps.
export default function ProductImagesEditor({ siteId, images, onChange }: {
  siteId: string
  images: ImageRow[]
  onChange: (images: ImageRow[]) => void
}) {
  const [adding, setAdding] = useState('')
  const move = (i: number, by: number) => {
    const next = [...images]
    const [row] = next.splice(i, 1)
    next.splice(i + by, 0, row)
    onChange(next)
  }
  const append = (raw: string) => {
    const url = raw.trim()
    if (!url || images.length >= MAX_IMAGES) return
    onChange([...images, { url, alt: '' }])
    setAdding('')
  }
  const add = () => append(adding)
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="mb-2 text-xs font-medium text-zinc-400">Pictures — the first is the cover</div>
      {images.length > 0 && (
        <ul className="mb-3 space-y-2">
          {images.map((img, i) => (
            <li key={`${img.url}-${i}`} className="flex items-center gap-2">
              <img src={img.url} alt="" className="h-10 w-10 shrink-0 rounded-lg border border-zinc-700 object-cover" />
              <input value={img.alt} onChange={(e) => onChange(images.map((x, j) => (j === i ? { ...x, alt: e.target.value } : x)))}
                placeholder={i === 0 ? 'Cover — describe it (optional)' : 'Describe it (optional)'} maxLength={250}
                aria-label={`Description of picture ${i + 1}`} className={input} />
              <button type="button" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move picture ${i + 1} up`} className="text-zinc-500 hover:text-zinc-200 disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
              <button type="button" onClick={() => move(i, 1)} disabled={i === images.length - 1} aria-label={`Move picture ${i + 1} down`} className="text-zinc-500 hover:text-zinc-200 disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button>
              <button type="button" onClick={() => onChange(images.filter((_, j) => j !== i))} aria-label={`Remove picture ${i + 1}`} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      )}
      {images.length < MAX_IMAGES ? (
        <div className="flex items-center gap-2">
          {/* An uploaded file joins the list at once: left in the field, a save would drop it. */}
          <ImageUpload siteId={siteId} value={adding} onChange={setAdding} onUploaded={append} placeholder="Upload or paste a picture link" className="flex-1" />
          <button type="button" onClick={add} disabled={!adding.trim()} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs font-medium text-emerald-400 hover:bg-zinc-800 disabled:opacity-40">Add</button>
        </div>
      ) : (
        <p className="text-xs text-zinc-500">{MAX_IMAGES} pictures is the most a product can have.</p>
      )}
    </div>
  )
}
