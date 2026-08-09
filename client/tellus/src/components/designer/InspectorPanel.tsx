// Right rail: the layer stack plus a property editor for the selection.
//
// Every edit here is a discrete user action, so all of them commit (one undo
// step each) — unlike a drag, which streams uncommitted updates.
import { ArrowDown, ArrowUp, Copy, Lock, Trash2, Unlock } from 'lucide-react'
import type { DesignLayer, FlyerDesign, FontManifestEntry } from '../../api/types'
import { layerLabel } from '../../utils/designer'
import { Input, Select } from '../ui'

export interface InspectorPanelProps {
  design: FlyerDesign
  selectedId: string | null
  onSelect: (id: string | null) => void
  onLayerChange: (id: string, patch: Partial<DesignLayer>) => void
  onDelete: (id: string) => void
  onDuplicate: (id: string) => void
  onReorder: (id: string, direction: 'up' | 'down') => void
  fonts: FontManifestEntry[]
}

function ColorRow({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-tu-dim">{label}</span>
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full cursor-pointer rounded-lg border border-tu-border bg-tu-panel2"
      />
    </label>
  )
}

export function InspectorPanel({
  design, selectedId, onSelect, onLayerChange, onDelete, onDuplicate, onReorder, fonts,
}: InspectorPanelProps) {
  const layer = design.layers.find((l) => l.id === selectedId) ?? null
  const patch = (p: Partial<DesignLayer>) => { if (layer) onLayerChange(layer.id, p) }

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-l border-tu-border bg-tu-panel">
      {/* Layer stack — rendered top-of-stack first, which is the reverse of
          the document array (later index = drawn on top). */}
      <div className="max-h-56 shrink-0 overflow-y-auto border-b border-tu-border p-2">
        <p className="px-1 pb-1 text-xs font-medium text-tu-faint">Layers</p>
        {design.layers.length === 0 && <p className="px-1 text-xs text-tu-faint">Empty canvas.</p>}
        {[...design.layers].reverse().map((l) => (
          <div
            key={l.id}
            className={`flex items-center gap-1 rounded px-1.5 py-1 text-xs ${
              l.id === selectedId ? 'bg-tu-panel2 text-tu-text' : 'text-tu-dim hover:bg-tu-panel2/60'
            }`}
          >
            <button className="flex-1 truncate text-left" onClick={() => onSelect(l.id)}>{layerLabel(l)}</button>
            <button className="text-tu-faint hover:text-tu-text" title={l.locked ? 'Unlock' : 'Lock'}
              onClick={() => onLayerChange(l.id, { locked: !l.locked } as Partial<DesignLayer>)}>
              {l.locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
            </button>
          </div>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {!layer ? (
          <p className="text-xs text-tu-faint">Select a layer to edit it. Double-click text to type.</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-tu-dim">{layerLabel(layer)}</span>
              <div className="flex items-center gap-1">
                <button className="rounded p-1 text-tu-faint hover:text-tu-text" title="Bring forward" onClick={() => onReorder(layer.id, 'up')}><ArrowUp className="h-3.5 w-3.5" /></button>
                <button className="rounded p-1 text-tu-faint hover:text-tu-text" title="Send backward" onClick={() => onReorder(layer.id, 'down')}><ArrowDown className="h-3.5 w-3.5" /></button>
                <button className="rounded p-1 text-tu-faint hover:text-tu-text" title="Duplicate" onClick={() => onDuplicate(layer.id)}><Copy className="h-3.5 w-3.5" /></button>
                <button className="rounded p-1 text-tu-bad/70 hover:text-tu-bad" title="Delete" onClick={() => onDelete(layer.id)}><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>

            {layer.type === 'text' && (
              <>
                <Select
                  label="Font"
                  value={layer.fontFamily}
                  onChange={(e) => patch({ fontFamily: e.target.value } as Partial<DesignLayer>)}
                  options={fonts.map((f) => ({ value: f.family, label: f.family }))}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input label="Size" type="number" min={8} max={400} value={layer.fontSize}
                    onChange={(e) => patch({ fontSize: Number(e.target.value) } as Partial<DesignLayer>)} />
                  <Select label="Weight" value={layer.fontStyle}
                    onChange={(e) => patch({ fontStyle: e.target.value as 'normal' | 'bold' | 'italic' } as Partial<DesignLayer>)}
                    options={[{ value: 'normal', label: 'Regular' }, { value: 'bold', label: 'Bold' }, { value: 'italic', label: 'Italic' }]} />
                </div>
                <Select label="Align" value={layer.align}
                  onChange={(e) => patch({ align: e.target.value as 'left' | 'center' | 'right' } as Partial<DesignLayer>)}
                  options={[{ value: 'left', label: 'Left' }, { value: 'center', label: 'Center' }, { value: 'right', label: 'Right' }]} />
                <div className="grid grid-cols-2 gap-2">
                  <Input label="Line height" type="number" step={0.05} min={0.7} max={3} value={layer.lineHeight}
                    onChange={(e) => patch({ lineHeight: Number(e.target.value) } as Partial<DesignLayer>)} />
                  <Input label="Tracking" type="number" step={1} min={-20} max={80} value={layer.letterSpacing}
                    onChange={(e) => patch({ letterSpacing: Number(e.target.value) } as Partial<DesignLayer>)} />
                </div>
                <ColorRow label="Colour" value={layer.fill} onChange={(v) => patch({ fill: v } as Partial<DesignLayer>)} />
              </>
            )}

            {layer.type === 'shape' && (
              <>
                <ColorRow label="Fill" value={layer.fill} onChange={(v) => patch({ fill: v } as Partial<DesignLayer>)} />
                {layer.shape === 'rect' && (
                  <Input label="Corner radius" type="number" min={0} max={400} value={layer.cornerRadius ?? 0}
                    onChange={(e) => patch({ cornerRadius: Number(e.target.value) } as Partial<DesignLayer>)} />
                )}
                {layer.shape === 'line' && (
                  <Input label="Thickness" type="number" min={1} max={200} value={layer.height}
                    onChange={(e) => patch({ height: Number(e.target.value) } as Partial<DesignLayer>)} />
                )}
              </>
            )}

            {layer.type === 'qr' && (
              <>
                <Input label="Size" type="number" min={96} max={2000} value={layer.size}
                  onChange={(e) => patch({ size: Number(e.target.value) } as Partial<DesignLayer>)} />
                <ColorRow label="Foreground" value={layer.fg} onChange={(v) => patch({ fg: v } as Partial<DesignLayer>)} />
                <ColorRow label="Background" value={layer.bg} onChange={(v) => patch({ bg: v } as Partial<DesignLayer>)} />
                <p className="text-xs text-tu-faint">
                  Keep strong contrast and leave the quiet zone clear — a low-contrast QR will not scan off paper.
                </p>
              </>
            )}

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-tu-dim">Opacity</span>
              <input
                type="range" min={0.1} max={1} step={0.05} value={layer.opacity}
                onChange={(e) => patch({ opacity: Number(e.target.value) } as Partial<DesignLayer>)}
                className="w-full accent-tu-accent"
              />
            </label>

            <div className="grid grid-cols-2 gap-2">
              <Input label="X" type="number" value={layer.x} onChange={(e) => patch({ x: Number(e.target.value) } as Partial<DesignLayer>)} />
              <Input label="Y" type="number" value={layer.y} onChange={(e) => patch({ y: Number(e.target.value) } as Partial<DesignLayer>)} />
            </div>
            <Input label="Rotation" type="number" min={-180} max={180} value={layer.rotation}
              onChange={(e) => patch({ rotation: Number(e.target.value) } as Partial<DesignLayer>)} />
          </>
        )}
      </div>
    </div>
  )
}
