import { useState } from 'react'
import { Crop, RotateCcw } from 'lucide-react'
import type { CappeAsset, StoryBlock } from '../../types'
import { IconBtn, Row, Select } from '../workspace/controls'
import { cropBetween } from './blocks'

type Photo = Extract<StoryBlock, { type: 'photo' }>

const clamp = (n: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, Math.round(n)))

/** The point of a pointer event inside `el`, in percent. */
function pointIn(el: HTMLElement, e: { clientX: number; clientY: number }) {
  const r = el.getBoundingClientRect()
  return { x: clamp(((e.clientX - r.left) / (r.width || 1)) * 100), y: clamp(((e.clientY - r.top) / (r.height || 1)) * 100) }
}

/** A size big enough to crop precisely, else the original. */
const previewUrl = (asset: CappeAsset) => asset.variants?.webp?.find((v) => v.w >= 960)?.url || asset.url

/** A photo block's frame: its shape, border and colour, and the part of the
 *  picture it keeps (dragged across the picture). Words, shapes and pictures
 *  on it are layers, placed on the page. */
export default function CropTool({ block, asset, onChange }: {
  block: Photo
  asset: CappeAsset
  onChange: (block: Photo) => void
}) {
  const [cropping, setCropping] = useState(false)
  const [drag, setDrag] = useState<{ from: { x: number; y: number }; to: { x: number; y: number } } | null>(null)
  const shape = block.shape || 'rect'
  const set = (patch: Partial<Photo>) => onChange({ ...block, ...patch })
  const shown = drag ? cropBetween(drag.from, drag.to) : block.crop
  return (
    <div className="space-y-2">
      <Row>
        <Select label="Shape" value={shape} onChange={(v) => set({ shape: v })}
          options={[{ key: 'rect', label: 'Rectangle' }, { key: 'rounded', label: 'Rounded' }, { key: 'circle', label: 'Circle' }, { key: 'arch', label: 'Arch' }]} />
        <Select label="Border" value={block.border || 'none'} onChange={(v) => set({ border: v })}
          options={[{ key: 'none', label: 'No border' }, { key: 'thin', label: 'Thin line' }, { key: 'thick', label: 'Thick (accent)' }, { key: 'mat', label: 'White mat' }]} />
      </Row>
      <Row>
        <Select label="Colour" value={block.filter || 'none'} onChange={(v) => set({ filter: v })}
          options={[{ key: 'none', label: 'As taken' }, { key: 'bw', label: 'Black and white' }, { key: 'sepia', label: 'Sepia' }]} />
        <div className="flex gap-1">
          <IconBtn title={cropping ? 'Done cropping' : 'Crop'} active={cropping} disabled={shape === 'circle'} onClick={() => setCropping((v) => !v)}>
            <Crop className="h-3.5 w-3.5" /><span className="ml-1">Crop</span>
          </IconBtn>
          {block.crop && <IconBtn title="The whole picture" onClick={() => set({ crop: null })}><RotateCcw className="h-3.5 w-3.5" /></IconBtn>}
        </div>
      </Row>
      {cropping && (
        <>
          <div className="relative cursor-crosshair select-none overflow-hidden rounded-md" data-testid="crop-area"
            onPointerDown={(e) => { const at = pointIn(e.currentTarget, e); setDrag({ from: at, to: at }) }}
            onPointerMove={(e) => { if (drag) setDrag({ ...drag, to: pointIn(e.currentTarget, e) }) }}
            onPointerUp={() => {
              const next = drag ? cropBetween(drag.from, drag.to) : null
              if (next) { set({ crop: next }); setCropping(false) }
              setDrag(null)
            }}>
            <img src={previewUrl(asset)} alt={asset.alt || ''} draggable={false} className="block w-full" />
            {shown && (
              <div className="pointer-events-none absolute border-2 border-emerald-400 shadow-[0_0_0_9999px_rgba(0,0,0,0.55)]"
                style={{ left: `${shown.x}%`, top: `${shown.y}%`, width: `${shown.w}%`, height: `${shown.h}%` }} />
            )}
          </div>
          <p className="text-[11px] text-zinc-500">Drag across the part of the picture to keep.</p>
        </>
      )}
    </div>
  )
}
