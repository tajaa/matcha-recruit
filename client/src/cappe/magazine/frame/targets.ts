import type { FrameTarget } from '../canvas/bridge'

/** What a click lands on, read from the markers the server prints in edit
 *  renders (services/magazine/story_render.py, pages.py, issue_render.py),
 *  and back from a target to its element on this page. */

const esc = (s: string) => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&'))

export const storyOf = (el: Element) => el.closest('[data-mz-s]')?.getAttribute('data-mz-s') ?? ''

export function blockOf(el: Element): number {
  const b = el.closest('[data-mz-b]')
  return b ? Number(b.getAttribute('data-mz-b')) : -1
}

export function targetOf(el: Element): FrameTarget {
  const c = el.closest('[data-mzc-el]')
  if (c) return { kind: 'cover', el: c.getAttribute('data-mzc-el') as Extract<FrameTarget, { kind: 'cover' }>['el'] }
  if (el.closest('.mz-issue__face')) return { kind: 'cover', el: 'photo' }
  if (el.closest('[data-mz-contents]')) return { kind: 'contents' }
  const b = el.closest('[data-mz-b]')
  if (b) {
    const story = storyOf(b), block = Number(b.getAttribute('data-mz-b'))
    // One picture of a photo group: its own design is what gets worked on.
    const item = b.classList.contains('mz-photos') ? el.closest('[data-mz-item]') : null
    return item ? { kind: 'block', story, block, item: Number(item.getAttribute('data-mz-item')) } : { kind: 'block', story, block }
  }
  const a = el.closest('[data-mz-s]')
  if (a) return { kind: 'story', story: a.getAttribute('data-mz-s') ?? '' }
  return { kind: 'none' }
}

export function elFor(t: FrameTarget | null | undefined): Element | null {
  if (!t) return null
  switch (t.kind) {
    case 'cover':
      return t.el === 'photo' ? document.querySelector('.mz-issue__face .mzc') : document.querySelector(`[data-mzc-el="${esc(t.el)}"]`)
    case 'contents': return document.querySelector('[data-mz-contents]')
    case 'block': case 'story': {
      const art = document.querySelector(`[data-mz-s="${esc(t.story)}"]`)
      if (t.kind === 'story') return art
      const block = art?.querySelector(`[data-mz-b="${t.block | 0}"]`) ?? null
      return t.item === undefined ? block : block?.querySelector(`[data-mz-item="${t.item | 0}"]`) ?? block
    }
    case 'layer': {
      const block = document.querySelector(`[data-mz-s="${esc(t.story)}"] [data-mz-b="${t.block | 0}"]`)
      const design = block?.querySelector(`.mzd[data-mzd="${t.item === null ? 'design' : `items.${t.item | 0}.design`}"]`)
      return design?.querySelector(`[data-mzd-l="${esc(t.ids[0] ?? '')}"]`) ?? null
    }
    default: return null
  }
}

/** Selected things get an outline; a story or nothing doesn't, and layers
 *  get their own frame with handles (layers.ts). */
export const outlined = (t: FrameTarget) => t.kind !== 'story' && t.kind !== 'none' && t.kind !== 'layer'
