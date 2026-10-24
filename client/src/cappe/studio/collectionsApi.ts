import { cappeApi } from '../api'
import type { CollectionCard, SavedCollection } from './model/collections'
import type { Doc } from './model/types'

const path = '/studio/collections'
export const collectionsApi = {
  list: () => cappeApi.get<CollectionCard[]>(path),
  open: (id: string) => cappeApi.get<SavedCollection>(`${path}/${id}`),
  save: (name: string, doc: Doc) => cappeApi.post<CollectionCard>(path, { name, doc }),
  remove: (id: string) => cappeApi.delete<void>(`${path}/${id}`),
}
