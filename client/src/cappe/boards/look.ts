// How notes and files look, shared by the board, its pins and the Studio's Board tab.

import type { NoteColor } from './limits'

export const NOTE_BG: Record<NoteColor, string> = {
  yellow: 'bg-amber-200 text-zinc-900',
  pink: 'bg-pink-200 text-zinc-900',
  blue: 'bg-sky-200 text-zinc-900',
  green: 'bg-emerald-200 text-zinc-900',
  purple: 'bg-violet-200 text-zinc-900',
  white: 'bg-zinc-50 text-zinc-900',
}

export function sizeLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}
