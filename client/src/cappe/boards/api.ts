// Mood boards over `server/app/cappe/routes/boards.py`. A pin's own pictures
// and files are signed links under the Cappe API (`/public/board-files/…`),
// shown through `fileUrl`; a library picture's are its CDN sizes.

import { cappeApi, cappeApiBase } from '../api'
import type { CappeAsset } from '../types'
import type { NoteColor } from './limits'

export type PinKind = 'image' | 'file' | 'note' | 'link'

export interface Board {
  id: string
  title: string
  pin_count: number
  covers: string[]
  created_at: string
  updated_at: string
}

export interface Pin {
  id: string
  board_id: string
  kind: PinKind
  x: number
  y: number
  w: number
  h: number
  rotation: number
  z: number
  asset_id: string | null
  in_library: boolean
  src: string | null
  full: string | null
  file_url: string | null
  alt: string | null
  filename: string | null
  mime: string | null
  size_bytes: number
  width: number | null
  height: number | null
  note: string | null
  color: NoteColor | null
  url: string | null
  title: string | null
  description: string | null
  site_name: string | null
  created_at: string
  updated_at: string
}

export interface BoardDetail {
  board: Board
  pins: Pin[]
  assets: CappeAsset[]
}

export interface Placed {
  x: number
  y: number
  w?: number
  h?: number
  rotation?: number
}

export type PinLayout = Pick<Pin, 'id' | 'x' | 'y' | 'w' | 'h' | 'rotation' | 'z'>

export interface ToLibrary {
  rights_attested: boolean
  ai_made?: boolean
  alt?: string
  credit_line?: string
}

/** A signed board link (a path under the API) or a CDN address, ready for `src`/`href`. */
export function fileUrl(link: string | null): string | null {
  if (!link) return null
  return link.startsWith('/') ? `${cappeApiBase}${link}` : link
}

const base = (siteId: string) => `/sites/${siteId}/boards`

export const boardsApi = {
  list: (siteId: string) => cappeApi.get<{ boards: Board[] }>(base(siteId)).then((r) => r.boards),
  create: (siteId: string, title: string) => cappeApi.post<Board>(base(siteId), { title }),
  rename: (siteId: string, boardId: string, title: string) =>
    cappeApi.patch<Board>(`${base(siteId)}/${boardId}`, { title }),
  remove: (siteId: string, boardId: string) => cappeApi.delete<null>(`${base(siteId)}/${boardId}`),
  get: (siteId: string, boardId: string) => cappeApi.get<BoardDetail>(`${base(siteId)}/${boardId}`),

  addNote: (siteId: string, boardId: string, at: Placed, note: string, color?: NoteColor) =>
    cappeApi.post<Pin>(`${base(siteId)}/${boardId}/pins`, { kind: 'note', ...at, note, color }),
  addLink: (siteId: string, boardId: string, at: Placed, url: string) =>
    cappeApi.post<Pin>(`${base(siteId)}/${boardId}/pins`, { kind: 'link', ...at, url }),
  addAsset: (siteId: string, boardId: string, at: Placed, assetId: string) =>
    cappeApi.post<Pin>(`${base(siteId)}/${boardId}/pins`, { kind: 'image', ...at, asset_id: assetId }),
  upload: (siteId: string, boardId: string, at: { x: number; y: number }, file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('x', String(Math.round(at.x)))
    form.append('y', String(Math.round(at.y)))
    return cappeApi.upload<Pin>(`${base(siteId)}/${boardId}/pins/upload`, form)
  },

  update: (siteId: string, boardId: string, pinId: string, changes: Partial<Pick<Pin,
    'x' | 'y' | 'w' | 'h' | 'rotation' | 'z' | 'note' | 'color' | 'title'>>) =>
    cappeApi.patch<Pin>(`${base(siteId)}/${boardId}/pins/${pinId}`, changes),
  layout: (siteId: string, boardId: string, pins: PinLayout[]) =>
    cappeApi.put<{ moved: number }>(`${base(siteId)}/${boardId}/layout`, { pins }),
  removePin: (siteId: string, boardId: string, pinId: string) =>
    cappeApi.delete<null>(`${base(siteId)}/${boardId}/pins/${pinId}`),
  toLibrary: (siteId: string, boardId: string, pinId: string, body: ToLibrary) =>
    cappeApi.post<{ pin: Pin; asset: CappeAsset }>(`${base(siteId)}/${boardId}/pins/${pinId}/library`, body),
}
