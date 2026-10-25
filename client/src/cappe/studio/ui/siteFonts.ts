// The magazine's own fonts in the Studio (ui/FontsDialog.tsx): grouped into
// families, and loaded into the store and the face book.

import { studioApi, type SiteFont } from '../api'
import type { StudioCtx } from './context'

/** A family's faces, the family named as it was last named. */
export function families(fonts: SiteFont[]): { key: string; name: string; faces: SiteFont[] }[] {
  const out = new Map<string, { key: string; name: string; faces: SiteFont[] }>()
  for (const f of fonts) {
    const row = out.get(f.family) ?? { key: f.family, name: f.name ?? 'Untitled font', faces: [] }
    row.faces.push(f)
    out.set(f.family, row)
  }
  for (const row of out.values()) row.faces.sort((a, b) => a.weight - b.weight || Number(a.italic) - Number(b.italic))
  return [...out.values()].sort((a, b) => a.name.localeCompare(b.name))
}

/** Load the magazine's fonts into the Studio (the store's list, and the faces
 *  it can measure and show). */
export async function loadSiteFonts(c: StudioCtx): Promise<void> {
  const { fonts } = await studioApi.fonts(c.siteId)
  c.fonts.book.add(fonts)
  c.store.set({ fonts })
}
