// Gummfit's photos in the side panel (server studio/bank.py, routes/library.py):
// browsed and searched here, and placed by making the site's library row for
// one, on the bank's own files, so there is no import to wait for.

import { cappeApi } from '../../../api'
import type { CappeAsset, CappeAssetVariants } from '../../../types'

export type BankPhoto = {
  id: string; name: string; url: string; variants: CappeAssetVariants; width: number; height: number
  credit_line: string | null; collection: string | null
}
export type BankPhotos = { total: number; items: BankPhoto[]; collections: string[] }

export const bankThumb = (p: BankPhoto) => p.variants?.webp?.[0]?.url || p.url

export const bankApi = {
  photos: (siteId: string, q: string, collection: string | null, offset = 0): Promise<BankPhotos> => {
    const params = new URLSearchParams({ q, offset: String(offset) })
    if (collection) params.set('collection', collection)
    return cappeApi.get<BankPhotos>(`/sites/${siteId}/library/bank?${params.toString()}`)
  },
  /** The site's library picture for a bank photo (the same one each time). */
  place: (siteId: string, id: string): Promise<CappeAsset> =>
    cappeApi.post<CappeAsset>(`/sites/${siteId}/library/bank/${id}`),
}
