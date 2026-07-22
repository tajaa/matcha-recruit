import { Loader2 } from 'lucide-react'
import type { CappeBlock, CappeCanvasElement } from '../../../types'
import { CanvasInspector, CanvasPanel } from './CanvasEditors'
import { isCanvasBlock } from './canvasHelpers'
import type { useCanvasBridge } from './useCanvasBridge'

export function CanvasModeView({
  preview, blocks, canvas,
  updateBlock, moveBlock, removeBlock, duplicateBlock, addBlockAt, addBlock,
  merlinOpen,
}: {
  preview: string
  blocks: CappeBlock[]
  canvas: ReturnType<typeof useCanvasBridge>
  updateBlock: (i: number, b: CappeBlock) => void
  moveBlock: (i: number, dir: -1 | 1) => void
  removeBlock: (i: number) => void
  duplicateBlock: (i: number) => void
  addBlockAt: (type: string, i: number) => void
  addBlock: (type: string) => void
  /** While Merlin is open, clicking a section still selects it (Merlin's own
   *  "Working on X" banner + selection context reads `canvas.selBlock`
   *  exactly as before) — but the manual field-editor popup is suppressed.
   *  Merlin's panel is now the primary way to act on a selection; showing
   *  both at once for the same click is exactly the redundant-modal
   *  confusion Merlin's UX pass exists to remove. */
  merlinOpen: boolean
}) {
  const {
    selBlock, setSelBlock, selElement, setSelElement, canvasBp, setCanvasBreakpoint,
    popPos, panelDragged, startPanelDrag, iframeRef, postToCanvas,
    patchCanvasElement, addCanvasElement, removeCanvasElement,
  } = canvas

  return (
    <div className="relative flex min-h-0 flex-1">
      <div className="hidden flex-1 justify-center overflow-auto bg-zinc-900 lg:flex">
        {preview ? (
          <iframe
            ref={iframeRef}
            title="Canvas"
            srcDoc={preview}
            sandbox="allow-scripts"
            className="h-full border-0 bg-white transition-[width] duration-200"
            style={
              canvasBp === 'm' && selBlock != null && isCanvasBlock(blocks[selBlock])
                ? { width: 414, maxWidth: '100%', boxShadow: '0 0 0 1px rgb(63 63 70)' }
                : { width: '100%' }
            }
          />
        ) : (
          <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
        )}
      </div>

      {/* floating editor — anchored to the clicked element when selected,
          else a corner card with the Add affordance + hint. Hidden while
          Merlin is open (see the `merlinOpen` prop doc) — a canvas-type
          block still needs CanvasInspector for its element-level editing
          (Merlin doesn't touch canvas elements), so that one stays. */}
      {(!merlinOpen || (selBlock != null && isCanvasBlock(blocks[selBlock]))) && (
        <div
          className="fixed z-40 hidden max-h-[74vh] w-[360px] overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl shadow-black/60 lg:block"
          style={selBlock != null ? { top: popPos.top, left: popPos.left } : { bottom: 16, left: 16 }}
        >
          {selBlock != null && isCanvasBlock(blocks[selBlock]) ? (
            <CanvasInspector
              block={blocks[selBlock]}
              elementId={selElement}
              bp={canvasBp}
              onSetBp={setCanvasBreakpoint}
              onPatchElement={(id: string, fn: (e: CappeCanvasElement) => CappeCanvasElement) => patchCanvasElement(selBlock, id, fn)}
              onAddElement={(k: CappeCanvasElement['kind']) => addCanvasElement(selBlock, k)}
              onRemoveElement={(id: string) => { removeCanvasElement(selBlock, id); postToCanvas({ type: 'cz-clear' }) }}
              onChangeBlock={(b: CappeBlock) => updateBlock(selBlock, b)}
              onHeaderPointerDown={startPanelDrag}
              onClose={() => { setSelBlock(null); setSelElement(null); panelDragged.current = false; postToCanvas({ type: 'cz-clear' }) }}
            />
          ) : (
            <CanvasPanel
              blocks={blocks}
              sel={selBlock}
              onChange={updateBlock}
              onMove={moveBlock}
              onRemove={removeBlock}
              onDuplicate={duplicateBlock}
              onAddAt={addBlockAt}
              onAdd={addBlock}
              onHeaderPointerDown={startPanelDrag}
              onClose={() => { setSelBlock(null); panelDragged.current = false; postToCanvas({ type: 'cz-clear' }) }}
            />
          )}
        </div>
      )}

      <div className="flex w-full items-center justify-center p-8 text-center text-sm text-zinc-500 lg:hidden">
        Canvas editing needs a wider screen — switch to Form mode or use a desktop.
      </div>
    </div>
  )
}
