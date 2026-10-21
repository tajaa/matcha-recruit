import { useRef, useState } from 'react'
import { Crop, Move, RotateCcw, Trash2, Type } from 'lucide-react'
import { ui } from '../../components/ui'
import type { CappeAsset, PhotoCrop, PhotoOverlay, StoryBlock } from '../../types'
import { cropBetween } from './blocks'

type Photo = Extract<StoryBlock, { type: 'photo' }>

const small = 'rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100'
const MAX_OVERLAYS = 8
const ALIGN = { center: 'text-center', left: 'text-left', right: 'text-right' } as const

/** A size big enough to place words on precisely, else the original. */
function previewUrl(asset: CappeAsset): string {
  return asset.variants?.webp?.find((v) => v.w >= 960)?.url || asset.url
}

const clamp = (n: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, Math.round(n)))

/** The point of a pointer event inside `el`, in percent. */
function pointIn(el: HTMLElement, e: { clientX: number; clientY: number }) {
  const r = el.getBoundingClientRect()
  return { x: clamp(((e.clientX - r.left) / (r.width || 1)) * 100), y: clamp(((e.clientY - r.top) / (r.height || 1)) * 100) }
}

/** The same frame the page draws (story_render.photo_html): the picture scaled
 *  so only the crop shows. */
function cropStyle(crop: PhotoCrop | null | undefined): React.CSSProperties {
  if (!crop) return {}
  return { position: 'absolute', maxWidth: 'none', width: `${10000 / crop.w}%`, height: `${10000 / crop.h}%`,
    left: `${(-100 * crop.x) / crop.w}%`, top: `${(-100 * crop.y) / crop.h}%` }
}

const OV_SIZE = { s: 'text-sm', m: 'text-xl', l: 'text-3xl', xl: 'text-5xl' } as const

/** A photo block's design: border, shape, colour, a crop dragged on the
 *  picture, and words placed on it by clicking where they go. */
export default function PhotoDesigner({ block, asset, onChange }: {
  block: Photo
  asset: CappeAsset
  onChange: (block: Photo) => void
}) {
  const [mode, setMode] = useState<'text' | 'crop'>('text')
  const [moving, setMoving] = useState<number | null>(null)
  const [drag, setDrag] = useState<{ from: { x: number; y: number }; to: { x: number; y: number } } | null>(null)
  const frame = useRef<HTMLDivElement>(null)
  const overlays = block.overlays || []
  const shape = block.shape || 'rect'
  const crop = shape === 'circle' ? null : block.crop || null
  const set = (patch: Partial<Photo>) => onChange({ ...block, ...patch })
  const setOverlay = (i: number, patch: Partial<PhotoOverlay>) =>
    set({ overlays: overlays.map((o, j) => (j === i ? { ...o, ...patch } : o)) })

  const place = (e: React.MouseEvent<HTMLDivElement>) => {
    if (mode !== 'text' || !frame.current || (e.target as HTMLElement).closest('[data-overlay]')) return
    const at = pointIn(frame.current, e)
    if (moving !== null) {
      setOverlay(moving, at)
      setMoving(null)
    } else if (overlays.length < MAX_OVERLAYS) {
      set({ overlays: [...overlays, { ...at, text: '', size: 'm', tone: 'light', box: false, align: 'center' }] })
    }
  }

  const aspect = crop && asset.width && asset.height ? `${asset.width * crop.w} / ${asset.height * crop.h}` : undefined
  const rounded = { rect: '', rounded: 'rounded-xl', circle: 'rounded-full aspect-square', arch: 'rounded-t-full' }[shape]
  const border = { none: '', thin: 'border border-zinc-500', thick: 'border-[6px] border-emerald-400', mat: 'border-[10px] border-white shadow' }[block.border || 'none']
  const filter = { none: '', bw: 'grayscale', sepia: 'sepia' }[block.filter || 'none']

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 text-sm text-zinc-300">
        <label className="flex items-center gap-2">Border
          <select value={block.border || 'none'} onChange={(e) => set({ border: e.target.value as Photo['border'] })} className={small}>
            <option value="none">None</option><option value="thin">Thin line</option>
            <option value="thick">Thick (accent colour)</option><option value="mat">White mat</option>
          </select>
        </label>
        <label className="flex items-center gap-2">Shape
          <select value={shape} onChange={(e) => set({ shape: e.target.value as Photo['shape'] })} className={small}>
            <option value="rect">Rectangle</option><option value="rounded">Rounded</option>
            <option value="circle">Circle</option><option value="arch">Arch</option>
          </select>
        </label>
        <label className="flex items-center gap-2">Colour
          <select value={block.filter || 'none'} onChange={(e) => set({ filter: e.target.value as Photo['filter'] })} className={small}>
            <option value="none">As taken</option><option value="bw">Black and white</option><option value="sepia">Sepia</option>
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Picture tools">
        <button type="button" aria-pressed={mode === 'text'} onClick={() => setMode('text')}
          className={`${ui.btnGhost} ${mode === 'text' ? 'border-emerald-500 text-emerald-300' : ''}`}><Type className="h-4 w-4" /> Words on the picture</button>
        <button type="button" aria-pressed={mode === 'crop'} disabled={shape === 'circle'} onClick={() => { setMode('crop'); setMoving(null) }}
          className={`${ui.btnGhost} ${mode === 'crop' ? 'border-emerald-500 text-emerald-300' : ''}`}><Crop className="h-4 w-4" /> Crop</button>
        {block.crop && (
          <button type="button" className={ui.btnGhost} onClick={() => set({ crop: null })}><RotateCcw className="h-4 w-4" /> Whole picture</button>
        )}
        <span className="text-xs text-zinc-500">
          {mode === 'crop' ? 'Drag across the part of the picture to keep.'
            : moving !== null ? 'Click where the words should go.'
              : overlays.length >= MAX_OVERLAYS ? `A photo holds ${MAX_OVERLAYS} pieces of text.` : 'Click the picture where words should go.'}
        </span>
      </div>

      {mode === 'crop' ? (
        <div className="relative cursor-crosshair select-none overflow-hidden rounded-lg" data-testid="crop-area"
          onPointerDown={(e) => { const at = pointIn(e.currentTarget, e); setDrag({ from: at, to: at }) }}
          onPointerMove={(e) => { if (drag) setDrag({ ...drag, to: pointIn(e.currentTarget, e) }) }}
          onPointerUp={() => {
            if (drag) {
              const next = cropBetween(drag.from, drag.to)
              if (next) { set({ crop: next }); setMode('text') }
            }
            setDrag(null)
          }}>
          <img src={previewUrl(asset)} alt={asset.alt || ''} draggable={false} className="block w-full" />
          {(() => {
            const r = drag ? cropBetween(drag.from, drag.to) : block.crop
            return r ? (
              <div className="pointer-events-none absolute border-2 border-emerald-400 shadow-[0_0_0_9999px_rgba(0,0,0,0.55)]"
                style={{ left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%` }} />
            ) : null
          })()}
        </div>
      ) : (
        <div ref={frame} onClick={place} data-testid="photo-frame" aria-label="Picture: click to place words"
          className={`relative cursor-copy overflow-hidden leading-none ${rounded} ${border}`} style={{ aspectRatio: aspect }}>
          <img src={previewUrl(asset)} alt={asset.alt || ''} draggable={false}
            className={`block w-full ${shape === 'circle' ? 'h-full object-cover' : ''} ${filter}`} style={cropStyle(crop)} />
          {overlays.map((o, i) => o.text.trim() || moving === i ? (
            <div key={i} data-overlay className={`pointer-events-none absolute max-w-[80%] -translate-x-1/2 -translate-y-1/2 font-bold leading-tight ${OV_SIZE[o.size]} ${o.tone === 'light' ? 'text-white drop-shadow' : 'text-zinc-900'} ${o.box ? (o.tone === 'light' ? 'bg-black/55 px-2 py-1' : 'bg-white/85 px-2 py-1') : ''} ${ALIGN[o.align]}`}
              style={{ left: `${o.x}%`, top: `${o.y}%`, whiteSpace: 'pre-line' }}>{o.text || '…'}</div>
          ) : (
            <span key={i} data-overlay className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-emerald-500"
              style={{ left: `${o.x}%`, top: `${o.y}%` }} />
          ))}
        </div>
      )}

      {overlays.length > 0 && (
        <ul className="space-y-2" aria-label="Words on the picture">
          {overlays.map((o, i) => (
            <li key={i} className="flex flex-wrap items-start gap-2 rounded-lg border border-zinc-800 p-2">
              <textarea value={o.text} onChange={(e) => setOverlay(i, { text: e.target.value })} rows={2} maxLength={300}
                placeholder="Words on the picture" aria-label={`Words ${i + 1}`} className={`${ui.input} min-w-[12rem] flex-1`} />
              <select value={o.size} onChange={(e) => setOverlay(i, { size: e.target.value as PhotoOverlay['size'] })} className={small} aria-label={`Size of words ${i + 1}`}>
                <option value="s">Small</option><option value="m">Medium</option><option value="l">Large</option><option value="xl">Huge</option>
              </select>
              <select value={o.tone} onChange={(e) => setOverlay(i, { tone: e.target.value as PhotoOverlay['tone'] })} className={small} aria-label={`Colour of words ${i + 1}`}>
                <option value="light">White</option><option value="dark">Dark</option>
              </select>
              <select value={o.align} onChange={(e) => setOverlay(i, { align: e.target.value as PhotoOverlay['align'] })} className={small} aria-label={`Alignment of words ${i + 1}`}>
                <option value="center">Centred</option><option value="left">Left</option><option value="right">Right</option>
              </select>
              <label className="flex items-center gap-1 text-sm text-zinc-300">
                <input type="checkbox" checked={o.box} onChange={(e) => setOverlay(i, { box: e.target.checked })} /> Box behind
              </label>
              <button type="button" className={ui.btnGhost} aria-pressed={moving === i} onClick={() => { setMode('text'); setMoving(moving === i ? null : i) }}>
                <Move className="h-4 w-4" /> Move
              </button>
              <button type="button" aria-label={`Remove words ${i + 1}`} className="p-1 text-zinc-500 hover:text-red-400"
                onClick={() => { set({ overlays: overlays.filter((_, j) => j !== i) }); setMoving(null) }}>
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
