// What every part of the Studio shares: its store, its faces, the text editor
// and the story it is designing.

import { createContext, useContext } from 'react'
import type { FontLoader } from '../fonts/loader'
import type { Store } from '../store/store'
import type { TextEditor } from '../text/editor'
import type { StudioPost } from '../api'

export type StudioCtx = {
  store: Store
  fonts: FontLoader
  editor: TextEditor
  siteId: string
  postId: string
  /** The story's own fields (title, access…), kept beside its document. */
  post: StudioPost
  setPost: (post: StudioPost) => void
  /** Save now (`keep`: as a version to go back to; `publish`: update the live story). */
  save: (opts?: { keep?: boolean; publish?: boolean }) => Promise<void>
  /** The board's element (pages and their lines), for the caret to read. */
  board: () => HTMLElement | null
  /** Scroll and zoom so a page fits (null: the spread showing). */
  fit: (page?: number | null, spread?: boolean) => void
  close: () => void
}

export const StudioContext = createContext<StudioCtx | null>(null)

export function useCtx(): StudioCtx {
  const ctx = useContext(StudioContext)
  if (!ctx) throw new Error('Outside the Studio')
  return ctx
}
