// What a drop or a paste puts on the board: files become photo or document
// pins, a web address a link card, any other words a note. Kept pure so the
// board page only has to read the event and hand it here.

import { MAX_FILE_BYTES, NOTE_MAX } from './limits'

export type Pasted =
  | { kind: 'files'; files: File[] }
  | { kind: 'link'; url: string }
  | { kind: 'note'; text: string }

const IMAGE = /^image\/(jpeg|png|gif|webp)$/
const DOCUMENT = new Set([
  'application/pdf', 'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/plain', 'text/csv',
])
const EXTENSIONS = /\.(jpe?g|png|gif|webp|pdf|docx?|xlsx?|txt|md|csv)$/i
const URLISH = /^(https?:\/\/\S+|www\.\S+\.\S+|[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}\/\S*)$/i

/** Whether the server will take this file (it checks the bytes again). */
export function pinnable(file: File): boolean {
  return IMAGE.test(file.type) || DOCUMENT.has(file.type) || EXTENSIONS.test(file.name)
}

export function tooBig(file: File): boolean {
  return file.size > MAX_FILE_BYTES
}

/** A single web address, or null. */
export function asUrl(text: string): string | null {
  const t = text.trim()
  return t && !/\s/.test(t) && URLISH.test(t) ? t : null
}

/** Words pasted or dropped: a link card for an address, a note otherwise. */
export function fromText(text: string): Pasted | null {
  const t = text.trim()
  if (!t) return null
  const url = asUrl(t)
  if (url) return { kind: 'link', url }
  return { kind: 'note', text: t.slice(0, NOTE_MAX) }
}

interface Transfer {
  files?: ArrayLike<File> | null
  items?: ArrayLike<{ kind: string; getAsFile: () => File | null }> | null
  getData: (type: string) => string
}

/** What a paste or a drop carries, files first (a copied screenshot also
 *  carries its file name as text, which is not what was meant). */
export function fromTransfer(data: Transfer | null): Pasted | null {
  if (!data) return null
  const files: File[] = Array.from(data.files ?? [])
  if (!files.length && data.items) {
    for (const item of Array.from(data.items)) {
      if (item.kind === 'file') {
        const f = item.getAsFile()
        if (f) files.push(f)
      }
    }
  }
  if (files.length) return { kind: 'files', files }
  const uri = data.getData('text/uri-list').split('\n').map((l) => l.trim()).find((l) => l && !l.startsWith('#'))
  if (uri && asUrl(uri)) return { kind: 'link', url: uri }
  return fromText(data.getData('text/plain'))
}

/** True while typing somewhere: a paste there is the field's, not the board's. */
export function typingIn(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || typeof el.tagName !== 'string') return false
  return el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)
}
