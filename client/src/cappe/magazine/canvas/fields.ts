import type { StoryBlock } from '../../types'

/** The words the page lets the owner type into (`data-mz-f`), as the server
 *  marks them (services/magazine/story_render.py, pages.py, issue_render.py).
 *  `#` is an item's index. tests/cappe/test_cappe_magazine_canvas.py reads
 *  these lists and checks every block type marks exactly these. */
export const BLOCK_FIELDS: Record<StoryBlock['type'], readonly string[]> = {
  cover: [],
  text: ['md'],
  photo: ['caption', 'overlays.#.text'],
  photos: ['items.#.caption'],
  quote: ['text', 'attribution'],
  sidebar: ['title', 'md'],
  qa: ['items.#.q', 'items.#.a_md'],
  divider: [],
  paywall: [],
}

/** A story's own lines (its header): the same on every page it is on. */
export const STORY_FIELDS = ['@title', '@kicker', '@excerpt', '@byline'] as const
export type StoryField = (typeof STORY_FIELDS)[number]

/** Written with the toolbar (bold, links, headings, lists): Markdown when
 *  stored. Every other field is plain words. */
export const RICH_FIELDS: readonly string[] = ['md', 'items.#.a_md']

/** The longest each field may be, as the server keeps it (story_schema.py,
 *  issue_schema.py, models/magazine.py). */
export const FIELD_MAX: Record<string, number> = {
  '@title': 255, '@kicker': 60, '@excerpt': 600, '@byline': 160,
  md: 20_000, caption: 500, 'overlays.#.text': 300, 'items.#.caption': 300, text: 400, attribution: 120,
  title: 120, 'items.#.q': 500, 'items.#.a_md': 5_000,
  'issue:lines.#.text': 140, 'issue:lines.#.sub': 200, 'issue:issue_line.text': 80, 'issue:contents.heading': 60,
  'issue:line': 200, 'issue:section': 40,
}
/** A sidebar's words are shorter than a text block's. */
export const SIDEBAR_MD_MAX = 4_000

/** A field path with its item index taken out (`items.2.q` → `items.#.q`, 2). */
export function fieldShape(path: string): { shape: string; index: number | null } {
  const m = /^([a-z_]+)\.(\d{1,3})\.([a-z_]+)$/.exec(path)
  return m ? { shape: `${m[1]}.#.${m[3]}`, index: Number(m[2]) } : { shape: path, index: null }
}

export const isStoryField = (path: string): path is StoryField => (STORY_FIELDS as readonly string[]).includes(path)

/** Whether a block of `type` has the field `path` (the shape the page sent). */
export function blockHasField(type: StoryBlock['type'], path: string): boolean {
  return BLOCK_FIELDS[type].includes(fieldShape(path).shape)
}

export const isRichField = (path: string) => RICH_FIELDS.includes(fieldShape(path).shape)
