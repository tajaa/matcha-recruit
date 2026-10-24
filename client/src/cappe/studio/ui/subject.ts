// Setting the subject in front from the Studio (model/subject.ts): the
// cut-out's silhouette read from its pixels (same origin, owner only), then
// the partner frame added in one undo step.

import { studioApi } from '../api'
import { shapeFromAlpha } from '../compose/wrap'
import { putSubjectInFront, subjectProblem } from '../model/subject'
import type { Asset, Shape } from '../model/types'
import type { StudioCtx } from './context'

const SIDE = 320 // the silhouette is read from a copy this wide at most

/** A cut-out's silhouette, row by row (compose/wrap.ts). */
export async function subjectShape(siteId: string, assetId: string): Promise<Shape> {
  const bitmap = await createImageBitmap(await studioApi.pixels(siteId, assetId))
  const scale = Math.min(1, SIDE / bitmap.width)
  const w = Math.max(1, Math.round(bitmap.width * scale)), h = Math.max(1, Math.round(bitmap.height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const g = canvas.getContext('2d', { willReadFrequently: true })
  if (!g) throw new Error('This browser can’t read the cut-out.')
  g.drawImage(bitmap, 0, 0, w, h)
  const ar = Math.round((bitmap.width / bitmap.height) * 10000) / 10000
  bitmap.close()
  return { ...shapeFromAlpha(g.getImageData(0, 0, w, h).data, w, h), ar }
}

/** The subject of frame `frame`'s photo set in front of the text over it. */
export async function placeSubject(c: StudioCtx, frame: string, cutout: Asset): Promise<void> {
  const problem = subjectProblem(c.store.get().doc, frame)
  if (problem) { c.store.set({ notice: problem }); return }
  try {
    const shape = await subjectShape(c.siteId, cutout.id)
    let made: string | null = null
    c.store.edit((d) => {
      const out = putSubjectInFront(d, frame, cutout, shape)
      made = out?.id ?? null
      return out?.doc ?? d
    })
    if (made) c.store.set({ selection: [made] })
  } catch (err) {
    c.store.set({ notice: err instanceof Error ? err.message : 'The subject couldn’t be set in front.' })
  }
}
