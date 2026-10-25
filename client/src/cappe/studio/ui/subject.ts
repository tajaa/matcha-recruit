// Setting the subject in front from the Studio (model/subject.ts): the
// cut-out's silhouette read from its pixels (same origin, owner only), then
// the partner frame added in one undo step.

import { studioApi } from '../api'
import { shapeFromAlpha } from '../compose/wrap'
import { backingFor, putSubjectInFront, subjectProblem } from '../model/subject'
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

/** The subject of frame `frame`'s photo set in front of the text over it
 *  (`backing`: the photo it was cut from, as the Picture Editor saved it). */
export async function placeSubject(c: StudioCtx, frame: string, cutout: Asset, backing?: string): Promise<void> {
  const problem = subjectProblem(c.store.get().doc, frame)
  if (problem) { c.store.set({ notice: problem }); return }
  const behind = backing ?? backingFor(c.store.get().assets, cutout)
  if (!behind) {
    c.store.set({ notice: 'This cut-out was cropped, turned or retouched in a way the photo isn’t. Use Cut out the subject and put it in front… to make both again.' })
    return
  }
  try {
    const shape = await subjectShape(c.siteId, cutout.id)
    let made: string | null = null
    c.store.edit((d) => {
      const out = putSubjectInFront(d, frame, cutout, shape, behind)
      made = out?.id ?? null
      return out?.doc ?? d
    })
    if (made) c.store.set({ selection: [made] })
  } catch (err) {
    c.store.set({ notice: err instanceof Error ? err.message : 'The subject couldn’t be set in front.' })
  }
}
