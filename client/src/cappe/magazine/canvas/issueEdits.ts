import type { CoverDesign } from '../../types'
import { place, round1, type IssueDoc } from '../issues/issueDoc'
import type { CoverEl } from './bridge'
import { FIELD_MAX, clip } from './fields'

const oneLine = (v: string, max: number) => clip(v.replace(/\s*\n\s*/g, ' '), max)

/** The issue with words typed on its cover or contents (`issue:` fields).
 *  `excerpts`: each story's dek, which the contents show until the story
 *  has a line of its own; typing it unchanged leaves the story without one.
 *  Null when the page named something the issue doesn't have. */
export function applyIssueEdit(doc: IssueDoc, field: string, value: string,
  excerpts: ReadonlyMap<string, string | null>): IssueDoc | null {
  const f = field.slice('issue:'.length)
  let m = /^lines\.(\d+)\.(text|sub)$/.exec(f)
  if (m) {
    const i = Number(m[1]), key = m[2] as 'text' | 'sub'
    const line = doc.cover.lines[i]
    if (!line) return null
    const words = oneLine(value, FIELD_MAX[`issue:lines.#.${key}`])
    if (line[key] === words) return doc
    return { ...doc, cover: { ...doc.cover, lines: doc.cover.lines.map((ln, j) => (j === i ? { ...ln, [key]: words } : ln)) } }
  }
  if (f === 'issue_line.text') {
    const words = oneLine(value, FIELD_MAX['issue:issue_line.text'])
    return doc.cover.issue_line.text === words ? doc
      : { ...doc, cover: { ...doc.cover, issue_line: { ...doc.cover.issue_line, text: words } } }
  }
  if (f === 'contents.heading') {
    const words = oneLine(value, FIELD_MAX['issue:contents.heading'])
    return doc.contents.heading === words ? doc : { ...doc, contents: { ...doc.contents, heading: words } }
  }
  m = /^(line|section):(.+)$/.exec(f)
  if (!m) return null
  const id = m[2]
  const at = doc.stories.findIndex((s) => s.post_id === id)
  if (at === -1) return null
  const words = oneLine(value, FIELD_MAX[`issue:${m[1]}`]).trim()
  if (m[1] === 'line') {
    const line = !words || words === (excerpts.get(id) || '').trim() ? null : words
    if (doc.stories[at].contents_line === line) return doc
    return { ...doc, stories: doc.stories.map((s, i) => (i === at ? { ...s, contents_line: line } : s)) }
  }
  // A section's heading names the stories under it: the run of stories from
  // this one that share its section.
  const old = doc.stories[at].section
  const next = words || null
  if (old === next) return doc
  let end = at
  while (end + 1 < doc.stories.length && doc.stories[end + 1].section === old) end += 1
  return { ...doc, stories: doc.stories.map((s, i) => (i >= at && i <= end ? { ...s, section: next } : s)) }
}

/** A cover element dragged to (x, y), or widened to `w`, in percent of the cover. */
export function moveCoverEl(cover: CoverDesign, el: CoverEl, x: number, y: number, w: number | null): CoverDesign | null {
  const change = { x: round1(x), y: round1(y), ...(w === null ? {} : { w: round1(w) }) }
  if (el === 'masthead') return { ...cover, masthead: place(cover.masthead, change) }
  if (el === 'issue_line') return { ...cover, issue_line: place(cover.issue_line, change) }
  const i = el.startsWith('line:') ? Number(el.slice(5)) : -1
  if (!cover.lines[i]) return null
  return { ...cover, lines: cover.lines.map((ln, j) => (j === i ? place(ln, change) : ln)) }
}

/** The part of the cover photo it keeps in view. */
export function coverFocal(cover: CoverDesign, x: number, y: number): CoverDesign {
  const pct = (n: number) => Math.round(Math.max(0, Math.min(100, n)))
  return { ...cover, photo: { ...cover.photo, focal: { x: pct(x), y: pct(y) } } }
}
