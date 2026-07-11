import { useState } from 'react'
import { Loader2, Plus, Sparkles } from 'lucide-react'
import type { CappeBlock } from '../../../../types/cappe'
import { BLOCK_ORDER, BLOCK_SCHEMAS } from './blockSchemas'
import { BlockCard } from './BlockCard'

export function FormModeView({
  blocks, preview, adding, setAdding, canvasUnlocked,
  updateBlock, removeBlock, moveBlock, reorderBlock, duplicateBlock, addBlock,
  copyStyle, pasteStyle, canPasteStyle,
}: {
  blocks: CappeBlock[]
  preview: string
  adding: boolean
  setAdding: (fn: (a: boolean) => boolean) => void
  canvasUnlocked: boolean
  updateBlock: (i: number, b: CappeBlock) => void
  removeBlock: (i: number) => void
  moveBlock: (i: number, dir: -1 | 1) => void
  reorderBlock: (from: number, to: number) => void
  duplicateBlock: (i: number) => void
  addBlock: (type: string) => void
  copyStyle: (i: number) => void
  pasteStyle: (i: number) => void
  canPasteStyle: boolean
}) {
  const [dragFrom, setDragFrom] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)

  const onDrop = (to: number) => {
    if (dragFrom !== null) reorderBlock(dragFrom, to)
    setDragFrom(null)
    setDragOver(null)
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="w-full overflow-y-auto border-r border-zinc-800 bg-zinc-950 p-5 lg:w-[46%]">
        <div className="space-y-3">
          {blocks.map((b, i) => (
            <div
              key={(b._k as string) || i}
              onDragOver={(e) => { if (dragFrom !== null) { e.preventDefault(); setDragOver(i) } }}
              onDrop={() => onDrop(i)}
              className={dragOver === i && dragFrom !== i ? 'rounded-xl ring-2 ring-emerald-500/60' : ''}
            >
              <BlockCard
                block={b}
                index={i}
                total={blocks.length}
                onChange={(nb) => updateBlock(i, nb)}
                onRemove={() => removeBlock(i)}
                onMove={(dir) => moveBlock(i, dir)}
                onDuplicate={() => duplicateBlock(i)}
                onCopyStyle={() => copyStyle(i)}
                onPasteStyle={() => pasteStyle(i)}
                canPasteStyle={canPasteStyle}
                onDragStart={() => setDragFrom(i)}
                onDragEnd={() => { setDragFrom(null); setDragOver(null) }}
              />
            </div>
          ))}
          {blocks.length === 0 && (
            <p className="rounded-xl border border-dashed border-zinc-700 p-6 text-center text-sm text-zinc-500">
              No blocks yet. Add one below to start building this page.
            </p>
          )}

          {/* add block */}
          <div className="relative">
            <button
              onClick={() => setAdding((a) => !a)}
              className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-700 py-3 text-sm font-semibold text-zinc-400 hover:border-emerald-500 hover:text-emerald-400"
            >
              <Plus className="h-4 w-4" /> Add block
            </button>
            {adding && (
              <div className="absolute z-10 mt-1 grid w-full grid-cols-2 gap-1 rounded-xl border border-zinc-700 bg-zinc-900 p-2 shadow-xl shadow-black/40">
                {BLOCK_ORDER.filter((t) => t !== 'canvas' || canvasUnlocked).map((t) => (
                  <button key={t} onClick={() => addBlock(t)} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-left text-sm text-zinc-300 hover:bg-emerald-500/10 hover:text-emerald-400">
                    {t === 'canvas' && <Sparkles className="h-3.5 w-3.5 text-amber-400" />}{BLOCK_SCHEMAS[t].label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* preview */}
      <div className="hidden flex-1 bg-zinc-900 lg:block">
        {preview ? (
          <iframe title="Live preview" srcDoc={preview} sandbox="allow-scripts" className="h-full w-full border-0" />
        ) : (
          <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
        )}
      </div>
    </div>
  )
}
