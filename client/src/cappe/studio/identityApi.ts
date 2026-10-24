import { cappeApi } from '../api'
import type { MagazineIdentity } from './model/types'

export type SavedIdentity = { rev: number; identity: MagazineIdentity | null }
const path = (siteId: string) => `/sites/${siteId}/studio/identity`
export const identityApi = {
  open: (siteId: string) => cappeApi.get<SavedIdentity>(path(siteId)),
  save: (siteId: string, identity: MagazineIdentity, baseRev: number) => cappeApi.put<SavedIdentity>(path(siteId), { identity, base_rev: baseRev }),
}
