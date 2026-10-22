import type { FrameTarget } from '../canvas/bridge'

/** What the editor on the page shares between its parts: what is selected,
 *  what is being typed into, and a way to put the outlines and handles back
 *  over what they belong to after anything moves. */

export type MzBook = { go: (spread: number, now?: boolean) => void; at: () => number; spreadOf: (el: Element) => number; refit: () => void }

declare global {
  interface Window { mzBook?: MzBook }
}

export const book = (): MzBook | undefined => window.mzBook

/** To the editor outside (it checks everything it is sent: canvas/bridge.ts). */
export const post = (m: Record<string, unknown>) => parent.postMessage(m, '*')

export const state = {
  selected: { kind: 'none' } as FrameTarget,
  selectedEl: null as Element | null,
  /** The field being typed into. */
  editing: null as HTMLElement | null,
  /** The words on a photo last clicked, which the grip moves. */
  overlay: null as Element | null,
  /** The block under the pointer. */
  hovered: null as Element | null,
}

const placers: (() => void)[] = []
/** Called whenever something may have moved on screen. */
export const onPlace = (fn: () => void) => { placers.push(fn) }
export const place = () => placers.forEach((fn) => fn())

export const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n))

/** An element of the editor's own, drawn over the page. */
export function ui<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag)
  el.className = `mze-ui ${cls}`
  document.body.appendChild(el)
  return el
}
