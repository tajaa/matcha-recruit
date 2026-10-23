// Dragging from the side panel onto a page. The browser carries only a
// marker type; what is being dragged waits here until the canvas takes the
// drop (canvas/Canvas.tsx), so it never has to round-trip through strings.

import type { DragEvent } from 'react'
import { cappeApi } from '../../../api'
import type { CappeAsset, CappeStockImports, CappeStockResult } from '../../../types'
import type { StudioCtx } from '../context'
import type { GraphicCard } from '../../model/graphics'
import { bankApi, type BankPhoto } from './bank'
import type { ElementSpec, TextStyle } from './catalog'
import { addElement, addGraphic, addPicture, addText, type At } from './place'

export const DRAG_TYPE = 'application/x-gummfit-studio'

export type Dragged =
  | { kind: 'element'; el: ElementSpec }
  | { kind: 'graphic'; g: GraphicCard }
  | { kind: 'text'; style: TextStyle }
  | { kind: 'asset'; asset: CappeAsset }
  | { kind: 'stock'; result: CappeStockResult }
  | { kind: 'bank'; photo: BankPhoto }

let current: Dragged | null = null

export function startDrag(e: DragEvent, what: Dragged): void {
  current = what
  e.dataTransfer.setData(DRAG_TYPE, what.kind)
  e.dataTransfer.effectAllowed = 'copy'
}

export function endDrag(): void {
  current = null
}

/** What is being dragged, if it came from the side panel. */
export function dragging(types: readonly string[]): Dragged | null {
  return types.includes(DRAG_TYPE) ? current : null
}

const POLL_MS = 1500
const MAX_POLLS = 80

/** An archive picture, imported into the library (or found there already)
 *  and handed back once it is in. */
export async function importStock(siteId: string, postId: string, r: CappeStockResult,
  wait = (ms: number) => new Promise((ok) => setTimeout(ok, ms))): Promise<CappeAsset> {
  let res = await cappeApi.post<CappeStockImports>(`/sites/${siteId}/library/import`,
    { items: [{ source: r.source, source_id: r.source_id }], post_id: postId })
  for (let n = 0; n <= MAX_POLLS; n++) {
    const job = res.imports[0]
    if (!job) break
    if (job.status === 'ready' && job.asset) return job.asset
    if (job.status === 'failed' || job.status === 'refused') throw new Error(job.error || 'That picture couldn’t be added.')
    await wait(POLL_MS)
    res = await cappeApi.get<CappeStockImports>(`/sites/${siteId}/library/imports?ids=${job.id}`)
  }
  throw new Error('That picture is taking a while. It will be in Your pictures when it’s ready.')
}

/** Put what was dropped where it landed; one that fails (an archive picture
 *  refused, the page gone) says why in the Studio's bar, since the tab it
 *  came from may not be open any more. */
export function dropOn(c: StudioCtx, what: Dragged, at: At): Promise<void> {
  return dropInto(c, what, at).catch((err) =>
    c.store.set({ notice: err instanceof Error && err.message ? err.message : 'Couldn’t add that to the page.' }))
}

/** Put what was dropped where it landed. */
export async function dropInto(c: StudioCtx, what: Dragged, at: At): Promise<void> {
  switch (what.kind) {
    case 'element': addElement(c, what.el, at); return
    case 'graphic': addGraphic(c, what.g, at); return
    case 'text': await addText(c, what.style, at); return
    case 'asset': addPicture(c, what.asset, at); return
    case 'stock': addPicture(c, await importStock(c.siteId, c.postId, what.result), at); return
    case 'bank': addPicture(c, await bankApi.place(c.siteId, what.photo.id), at)
  }
}
