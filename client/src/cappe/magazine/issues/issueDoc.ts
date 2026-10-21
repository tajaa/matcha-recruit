import type {
  CappeMagazineIssue, CappeMagazineIssueOptions, ContentsDesign, CoverDesign, CoverElement, CoverLine, IssueStoryRef,
} from '../../types'
import type { StoryDoc } from '../canvas/storyDoc'
import { MASTHEAD_EM, MAX_LINES, MAX_SIZE, MIN_SIZE, MIN_WIDTH } from './coverVocab'

/** What the issue editor edits, as one document with undo and redo. */
export type IssueDoc = {
  title: string
  number: number
  cover: CoverDesign
  contents: ContentsDesign
  stories: IssueStoryRef[]
  /** Stories edited on the issue's pages, unsaved, by id (saved with the issue). */
  drafts?: Record<string, StoryDoc>
}

export const docOf = (issue: CappeMagazineIssue): IssueDoc => ({
  title: issue.title || '',
  number: issue.number,
  cover: issue.cover,
  contents: issue.contents,
  stories: issue.stories.map(({ post_id, section, contents_line }) => ({ post_id, section, contents_line })),
})

/** The PUT body (and, with the issue's id, the preview's). */
export const saveBody = (doc: IssueDoc) => ({
  title: doc.title.trim() || null,
  number: doc.number,
  cover: doc.cover,
  contents: doc.contents,
  stories: doc.stories.map((s) => ({
    post_id: s.post_id, section: s.section?.trim() || null, contents_line: s.contents_line?.trim() || null,
  })),
})

/** One decimal, half up: as the server rounds, so a value never differs. */
export const round1 = (n: number) => Math.floor(n * 10 + 0.5) / 10
export const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n))

/** Move an element and keep its box on the cover (as the server does). */
export function place<T extends CoverElement>(el: T, change: Partial<Pick<CoverElement, 'x' | 'y' | 'w'>>): T {
  const w = round1(clamp(change.w ?? el.w, MIN_WIDTH, 100))
  return { ...el, w, x: round1(clamp(change.x ?? el.x, 0, 100 - w)), y: round1(clamp(change.y ?? el.y, 0, 100)) }
}

/** The masthead no larger than fits the magazine's name on one line (the
 *  server's `fit_masthead`). */
export function fitMasthead(cover: CoverDesign, name: string): CoverDesign {
  const chars = Math.max(name.trim().length, 1)
  const fits = round1(clamp(cover.masthead.w / (chars * MASTHEAD_EM), MIN_SIZE, MAX_SIZE))
  return { ...cover, masthead: { ...cover.masthead, size: Math.min(cover.masthead.size, fits) } }
}

/** Choose a template: its places and type, keeping the photo, the issue
 *  line's words and each cover line's words and link (moved into the
 *  template's slots in order; lines beyond them keep their own places). */
export function applyTemplate(cover: CoverDesign, template: CappeMagazineIssueOptions['templates'][number],
  name: string): CoverDesign {
  const t = template.cover
  const lines = cover.lines.map((ln, i) => {
    const slot = t.lines[i]
    return slot ? { ...slot, text: ln.text, sub: ln.sub, post_id: ln.post_id } : ln
  })
  return fitMasthead({
    ...t,
    template: template.key,
    photo: cover.photo,
    issue_line: { ...t.issue_line, text: cover.issue_line.text, hidden: cover.issue_line.hidden },
    lines,
  }, name)
}

/** A new cover line under the last, in the server's default look. */
export function newLine(cover: CoverDesign): CoverLine | null {
  if (cover.lines.length >= MAX_LINES) return null
  const last = cover.lines[cover.lines.length - 1]
  return {
    x: last?.x ?? 6, y: round1(clamp((last?.y ?? 48) + 12, 0, 92)), w: last?.w ?? 60,
    size: 4.4, color: '#ffffff', align: last?.align ?? 'left', weight: 'bold', case: 'asis', italic: false,
    tracking: 'normal', font: 'heading', text: 'New cover line', sub: '', post_id: null, box: 'none', box_color: '#000000',
  }
}

export function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

/** Take a story out of the issue, and any cover line's link to it. */
export function removeStory(doc: IssueDoc, postId: string): IssueDoc {
  return {
    ...doc,
    stories: doc.stories.filter((s) => s.post_id !== postId),
    cover: { ...doc.cover, lines: doc.cover.lines.map((ln) => (ln.post_id === postId ? { ...ln, post_id: null } : ln)) },
  }
}

/** Add stories at the end, each once. */
export function addStories(doc: IssueDoc, postIds: string[]): IssueDoc {
  const have = new Set(doc.stories.map((s) => s.post_id))
  const added = postIds.filter((id) => !have.has(id)).map((post_id) => ({ post_id, section: null, contents_line: null }))
  return added.length ? { ...doc, stories: [...doc.stories, ...added] } : doc
}
