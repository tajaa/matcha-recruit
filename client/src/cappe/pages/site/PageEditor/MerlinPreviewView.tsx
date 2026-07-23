import { Loader2 } from 'lucide-react'
import type { RefObject } from 'react'

/** The editing surface while Merlin is the active editor. Merlin, Canvas, and
 *  Form are mutually exclusive (index.tsx renders exactly one) — this is
 *  intentionally just the live preview, full width, with no block-list panel
 *  and no floating field editor. Merlin's own panel is the only place edits
 *  happen; showing a second editing surface alongside it was the "3 panes
 *  open at once" confusion this replaces.
 *
 *  Selection and drag-drop-image-onto-a-section still work here: both ride
 *  the framed runtime's postMessage bridge (useCanvasBridge), which is
 *  mounted independently of which view is on screen. */
export function MerlinPreviewView({
  preview, iframeRef,
}: {
  preview: string
  iframeRef: RefObject<HTMLIFrameElement | null>
}) {
  return (
    <div className="flex min-h-0 flex-1 justify-center overflow-auto bg-zinc-900">
      {preview ? (
        <iframe
          ref={iframeRef}
          title="Live preview"
          srcDoc={preview}
          sandbox="allow-scripts"
          className="h-full w-full border-0 bg-white"
        />
      ) : (
        <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
      )}
    </div>
  )
}
