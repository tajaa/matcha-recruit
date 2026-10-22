import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { generateJSON } from '@tiptap/core'
import cases from '../../../../server/tests/cappe/fixtures/magazine_rt_cases.json'
import StoryEditor from './editor/StoryEditor'
import IssueEditor from './issues/IssueEditor'
import { newBlock } from './editor/blocks'
import { docOf } from './issues/issueDoc'
import EditFrame from './canvas/EditFrame'
import { PHONE, SPREAD_MIN, fitFrame } from './canvas/fit'
import { readMessage, type FrameMessage } from './canvas/bridge'
import { BLOCK_FIELDS, blockHasField, fieldShape, isRichField } from './canvas/fields'
import { cleanHref, cleanRt, emptyRt, richPatch, rtText, rtToMd, type RtDoc } from './canvas/rt'
import { richExtensions } from './frame/extensions'
import { applyIssueEdit, coverFocal, moveCoverEl } from './canvas/issueEdits'
import { applyEdit, storyFromMessage, withPicture, type StoryDoc } from './canvas/storyDoc'
import type {
  CappeMagazineIssue, CappeMagazineIssueOptions, CappePost, ContentsDesign, CoverDesign, CoverElement, CoverLine, StoryBlock,
} from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const ctx = { stories: new Set(['preview', 'p-1']) }
type Mark = 'bold' | 'italic' | 'underline' | 'strike' | { type: 'link'; attrs: { href: string } }
const t = (text: string, ...marks: Mark[]) =>
  (marks.length ? { type: 'text' as const, text, marks: marks.map((m) => (typeof m === 'string' ? { type: m } : m)) } : { type: 'text' as const, text })
const doc = (...inline: ReturnType<typeof t>[]): RtDoc => ({ type: 'doc', content: [{ type: 'paragraph', content: inline }] }) as RtDoc
const text = (md: string): StoryBlock => ({ ...(newBlock('text') as Extract<StoryBlock, { type: 'text' }>), md, rt: doc(t(md)) })
const photo = (over: Partial<Extract<StoryBlock, { type: 'photo' }>> = {}): StoryBlock =>
  ({ ...(newBlock('photo') as Extract<StoryBlock, { type: 'photo' }>), ...over })

const story = (): StoryDoc => ({
  fields: { title: 'Low tide', kicker: '', excerpt: 'Boats.', byline: 'Ana', topic: '', layout: 'standard', status: 'draft', access: 'free' },
  blocks: [newBlock('cover'), text('First words.'),
    photo({ asset_id: 'a-1', caption: 'Dawn', overlays: [{ x: 50, y: 50, text: 'Hi', size: 'm', tone: 'light', box: false, align: 'center' }] }),
    { type: 'photos', layout: 'pair', items: [{ asset_id: null, caption: '' }, { asset_id: 'a-1', caption: 'Two' }] },
    { type: 'qa', items: [{ q: 'Why?', a_md: 'Because.' }] }],
})

describe('rich text, as the server keeps it (the shared fixture)', () => {
  for (const c of cases) {
    it(`keeps ${c.name}`, () => {
      const rt = c.rt as unknown as RtDoc
      expect(cleanRt(rt)).toEqual(rt)
      expect(rtToMd(rt)).toBe(c.md)
      // The editor reads the page's HTML back into the same document.
      expect(cleanRt(generateJSON(c.html, richExtensions()))).toEqual(rt)
    })
  }

  it('keeps only what the server keeps', () => {
    const raw = { type: 'doc', content: [
      { type: 'paragraph', content: [
        { type: 'text', text: 'a', marks: [{ type: 'italic' }, { type: 'bold' }, { type: 'bold' }, { type: 'code' }] },
        { type: 'text', text: 'b', marks: [{ type: 'bold' }, { type: 'italic' }] },
        { type: 'text', text: 'c', marks: [{ type: 'link', attrs: { href: 'javascript:alert(1)', target: '_blank' } }] },
        { type: 'text', text: 'd', marks: [{ type: 'link', attrs: { href: ' https://example.com ', class: 'x' } }] },
        { type: 'image', attrs: { src: 'https://evil.test/x.png' } }, 7, null],
      },
      { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'Big' }] },
      { type: 'heading', attrs: { level: 5 } },
      { type: 'codeBlock', content: [{ type: 'text', text: 'x()' }] },
      { type: 'blockquote', content: [{ type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'Said' }] }] },
      { type: 'blockquote', content: [] },
      { type: 'orderedList', attrs: { start: 0 }, content: [{ type: 'listItem', content: [{ type: 'bulletList', content: [
        { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'in' }] }] }] }] }, { type: 'listItem', content: [] }] },
      { type: 'bulletList', content: [] },
    ] }
    expect(cleanRt(raw)).toEqual({ type: 'doc', content: [
      { type: 'paragraph', content: [t('ab', 'bold', 'italic'), t('c'), t('d', { type: 'link', attrs: { href: 'https://example.com' } })] },
      { type: 'heading', attrs: { level: 2 }, content: [t('Big')] },
      { type: 'heading', attrs: { level: 3 } },
      { type: 'paragraph', content: [t('x()')] },
      { type: 'blockquote', content: [{ type: 'paragraph', content: [t('Said')] }] },
      { type: 'orderedList', attrs: { start: 1 }, content: [{ type: 'listItem', content: [
        { type: 'paragraph' }, { type: 'bulletList', content: [{ type: 'listItem', content: [{ type: 'paragraph', content: [t('in')] }] }] }] }] },
    ] })
    expect(cleanRt(null)).toBeNull()
    expect(cleanRt({ type: 'p' })).toBeNull()
    expect(cleanRt({ type: 'doc', content: 'x' })).toEqual(emptyRt())
    expect(cleanRt(doc(t('a'.repeat(30)), t('b'.repeat(30))), 40)).toEqual(doc(t(`${'a'.repeat(30)}${'b'.repeat(10)}`)))
    let deep: unknown = { type: 'text', text: 'x' }
    for (let i = 0; i < 9; i++) deep = { type: 'span', content: [deep] }
    expect(cleanRt({ type: 'doc', content: [{ type: 'paragraph', content: [deep] }] })).toEqual({ type: 'doc', content: [{ type: 'paragraph' }] })
    for (const bad of ['javascript:x', 'data:text/html,x', '/here', 'https://a\nb', '', 3]) expect(cleanHref(bad)).toBeNull()
    expect(cleanHref('mailto:desk@example.com')).toBe('mailto:desk@example.com')
  })

  it('reads its words and keeps a field within its length', () => {
    expect(rtText({ type: 'doc', content: [{ type: 'heading', attrs: { level: 2 }, content: [t('At sea')] },
      { type: 'paragraph', content: [t('Line'), { type: 'hardBreak' }, t('two')] }] })).toBe('At sea Line two')
    expect(rtText(null)).toBe('')
    expect(richPatch(doc(t('x'.repeat(50), 'bold')), 20)).toEqual({ rt: doc(t('x'.repeat(20), 'bold')), md: `**${'x'.repeat(18)}` })
    expect(richPatch('nope', 20)).toEqual({ rt: emptyRt(), md: '' })
  })
})

describe('the field allowlist', () => {
  it('reads item indexes out of a path', () => {
    expect(fieldShape('items.12.caption')).toEqual({ shape: 'items.#.caption', index: 12 })
    expect(fieldShape('md')).toEqual({ shape: 'md', index: null })
  })
  it('knows which block has which words, and which are written with the toolbar', () => {
    expect(blockHasField('text', 'md')).toBe(true)
    expect(blockHasField('text', 'caption')).toBe(false)
    expect(blockHasField('photo', 'overlays.3.text')).toBe(true)
    expect(blockHasField('qa', 'items.0.a_md')).toBe(true)
    expect(BLOCK_FIELDS.divider).toEqual([])
    expect(isRichField('items.4.a_md')).toBe(true)
    expect(isRichField('caption')).toBe(false)
  })
})

describe('readMessage', () => {
  it('takes well-formed messages about the stories on the page', () => {
    expect(readMessage({ type: 'mz-select', target: { kind: 'block', story: 'p-1', block: 3 } }, ctx))
      .toEqual({ type: 'mz-select', target: { kind: 'block', story: 'p-1', block: 3 } })
    expect(readMessage({ type: 'mz-edit', story: 'preview', block: -1, field: '@title', value: 'Hi', rich: false }, ctx))
      .toMatchObject({ field: '@title', block: -1 })
    expect(readMessage({ type: 'mz-edit', story: 'x', block: -1, field: 'issue:lines.0.text', value: 'Hi', rich: false }, ctx))
      .toMatchObject({ story: '', block: -1, field: 'issue:lines.0.text' })
    expect(readMessage({ type: 'mz-move', target: { kind: 'cover', el: 'line:2' }, x: 140, y: -3, w: 40 }, ctx))
      .toEqual({ type: 'mz-move', target: { kind: 'cover', el: 'line:2' }, x: 100, y: 0, w: 40 })
    expect(readMessage({ type: 'mz-move', target: { kind: 'overlay', story: 'p-1', block: 2, overlay: 'overlays.1' }, x: 5, y: 6 }, ctx))
      .toEqual({ type: 'mz-move', target: { kind: 'overlay', story: 'p-1', block: 2, overlay: 1 }, x: 5, y: 6, w: null })
    expect(readMessage({ type: 'mz-pick', story: 'p-1', block: 3, item: null }, ctx)).toMatchObject({ item: null })
    // A rich field's document arrives cleaned to what the server keeps.
    const sent = { type: 'doc', content: [{ type: 'paragraph', content: [
      { type: 'text', text: 'Hi', marks: [{ type: 'bold' }, { type: 'link', attrs: { href: 'javascript:x' } }] }] }, { type: 'image' }] }
    expect(readMessage({ type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: sent, rich: true }, ctx))
      .toEqual({ type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: doc(t('Hi', 'bold')), rich: true })
    expect(readMessage({ type: 'mz-key', key: 'undo' }, ctx)).toEqual({ type: 'mz-key', key: 'undo' })
  })

  it('refuses anything else', () => {
    const bad: unknown[] = [
      null, 'mz-ready', { type: 'mz-nope' },
      { type: 'mz-select', target: { kind: 'block', story: 'someone-else', block: 1 } },
      { type: 'mz-select', target: { kind: 'block', story: 'p-1', block: 1.5 } },
      { type: 'mz-select', target: { kind: 'block', story: 'p-1', block: 500 } },
      { type: 'mz-select', target: { kind: 'cover', el: 'script' } },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'items.0.__proto__.x', value: 'x', rich: false },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'constructor.prototype', value: 'x', rich: false },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: '<p>x</p>', rich: true },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: doc(t('x'.repeat(200_001))), rich: true },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: 42, rich: true },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: doc(t('x')), rich: 'yes' },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'caption', value: 'x'.repeat(20_001), rich: false },
      { type: 'mz-edit', story: 'p-1', block: -1, field: 'issue:lines.0.text', value: doc(t('x')), rich: true },
      { type: 'mz-edit', story: 'p-1', block: 1, field: 'issue:line:not-a-uuid', value: 'x', rich: false },
      { type: 'mz-insert', story: 'p-1', at: 2, kind: 'cover' },
      { type: 'mz-insert', story: 'p-1', at: -1, kind: 'text' },
      { type: 'mz-pick', story: 'p-1', block: 1, item: 'all' },
      { type: 'mz-move', target: { kind: 'cover', el: 'photo' }, x: 1, y: 1 },
      { type: 'mz-move', target: { kind: 'cover', el: 'masthead' }, x: Number.NaN, y: 1 },
      { type: 'mz-move', target: { kind: 'overlay', story: 'p-1', block: 2, overlay: 'items.1' }, x: 1, y: 1 },
      { type: 'mz-key', key: 'rm -rf' },
    ]
    for (const b of bad) expect(readMessage(b, ctx)).toBeNull()
  })
})

describe('a story edited on its page', () => {
  it('takes words into the header and the blocks', () => {
    const d = story()
    expect(applyEdit(d, -1, '@title', 'High\ntide')!.fields.title).toBe('High tide')
    const words = doc(t('New '), t('words', 'bold'))
    expect(applyEdit(d, 1, 'md', words)!.blocks[1]).toMatchObject({ md: 'New **words**', rt: words })
    expect(applyEdit(d, 2, 'caption', 'Morning')!.blocks[2]).toMatchObject({ caption: 'Morning' })
    expect(applyEdit(d, 2, 'overlays.0.text', 'Two\nlines')!.blocks[2]).toMatchObject({ overlays: [{ text: 'Two\nlines' }] })
    expect(applyEdit(d, 3, 'items.1.caption', 'Second')!.blocks[3]).toMatchObject({ items: [{ caption: '' }, { caption: 'Second' }] })
    expect(applyEdit(d, 4, 'items.0.a_md', doc(t('Yes')))!.blocks[4]).toMatchObject({ items: [{ q: 'Why?', a_md: 'Yes', a_rt: doc(t('Yes')) }] })
    expect(applyEdit(d, -1, '@kicker', 'x'.repeat(90))!.fields.kicker).toHaveLength(60)
    expect(applyEdit(d, 1, 'md', doc(t('First words.')))).toBe(d)  // unchanged: the same document
    // A sidebar's words are shorter than a text block's.
    const side = { ...d, blocks: [...d.blocks, { type: 'sidebar' as const, title: '', md: '' }] }
    expect(applyEdit(side, 5, 'md', doc(t('x'.repeat(5_000))))!.blocks[5]).toMatchObject({ md: 'x'.repeat(4_000) })
  })

  it('drops an edit naming what the story does not have', () => {
    const d = story()
    expect(applyEdit(d, 1, 'caption', 'x')).toBeNull()  // a text block has no caption
    expect(applyEdit(d, 1, 'md', 'x')).toBeNull()  // text arrives as a document
    expect(applyEdit(d, 2, 'caption', doc(t('x')))).toBeNull()
    expect(applyEdit(d, 9, 'md', doc(t('x')))).toBeNull()
    expect(applyEdit(d, 3, 'items.5.caption', 'x')).toBeNull()
    expect(applyEdit(d, 4, 'items.3.a_md', doc(t('x')))).toBeNull()
    expect(applyEdit(d, -1, '@title', doc(t('x')))).toBeNull()
  })

  it('adds blocks after the cover, moves words on a photo, focuses the cover', () => {
    const d = story()
    const added = storyFromMessage(d, { type: 'mz-insert', story: 'p-1', at: 0, kind: 'quote' })!
    expect(added).toMatchObject({ step: true, select: 1 })
    expect(added.doc.blocks.map((b) => b.type)).toEqual(['cover', 'quote', 'text', 'photo', 'photos', 'qa'])
    const moved = storyFromMessage(d, { type: 'mz-move', target: { kind: 'overlay', story: 'p-1', block: 2, overlay: 0 }, x: 12.6, y: 80, w: null })!
    expect(moved.doc.blocks[2]).toMatchObject({ overlays: [{ x: 13, y: 80 }] })
    expect(storyFromMessage(d, { type: 'mz-move', target: { kind: 'overlay', story: 'p-1', block: 1, overlay: 0 }, x: 1, y: 1, w: null })).toBeNull()
    const focused = storyFromMessage(d, { type: 'mz-focal', target: { kind: 'block', story: 'p-1', block: 0 }, x: 20, y: 70 })!
    expect(focused.doc.blocks[0]).toMatchObject({ focal: { x: 20, y: 70 } })
    expect(storyFromMessage(d, { type: 'mz-focal', target: { kind: 'block', story: 'p-1', block: 1 }, x: 2, y: 2 })).toBeNull()
    const typed = storyFromMessage(d, { type: 'mz-edit', story: 'p-1', block: 1, field: 'md', value: doc(t('Hey')), rich: true })!
    expect(typed.step).toBe(false)
    expect(storyFromMessage(d, { type: 'mz-ready' })).toBeNull()
  })

  it('puts a chosen picture where it was asked for', () => {
    const d = story()
    expect(withPicture(d.blocks[2], 'a-9', null)).toMatchObject({ asset_id: 'a-9' })
    expect(withPicture(d.blocks[3], 'a-9', 1)).toMatchObject({ items: [{ asset_id: null }, { asset_id: 'a-9' }] })
    expect(withPicture(d.blocks[3], 'a-9', null)).toMatchObject({ items: [{ asset_id: 'a-9' }, { asset_id: 'a-1' }] })
    expect(withPicture(d.blocks[1], 'a-9', null)).toBe(d.blocks[1])
  })
})

// ── issues ───────────────────────────────────────────────────────────────────

const el = (over: Partial<CoverElement> = {}): CoverElement => ({
  x: 4, y: 3, w: 92, size: 16, color: '#ffffff', align: 'center', weight: 'black', case: 'upper', italic: false,
  tracking: 'tight', font: 'heading', ...over,
})
const line = (over: Partial<CoverLine> = {}): CoverLine => ({
  ...el({ x: 6, y: 60, w: 60, size: 6, align: 'left' }), text: 'Low tide', sub: '', post_id: null, box: 'none', box_color: '#000000', ...over,
})
const cover: CoverDesign = {
  v: 1, template: 'classic', background: '#1b1916', photo: { asset_id: null, focal: { x: 50, y: 50 }, zoom: 100, filter: 'none' },
  scrim: { kind: 'top', strength: 45 }, masthead: el(),
  issue_line: { ...el({ y: 20, size: 2.4 }), text: '', hidden: false }, lines: [line()], credit: { corner: 'br', tone: 'light' },
}
const contents: ContentsDesign = {
  v: 1, layout: 'list', heading: 'In this issue', show_numbers: true, show_pictures: true, show_deks: true, show_bylines: false, accent: 'accent',
}
const P1 = '11111111-1111-4111-8111-111111111111'
const P2 = '22222222-2222-4222-8222-222222222222'
const P3 = '33333333-3333-4333-8333-333333333333'
const issue = (over: Partial<CappeMagazineIssue> = {}): CappeMagazineIssue => ({
  id: 'i-1', number: 3, title: 'The tide issue', status: 'draft', released_at: null, cover, contents,
  stories: [P1, P2, P3].map((id, i) => ({ post_id: id, section: i < 2 ? 'Features' : 'Dispatches', contents_line: null,
    title: `Story ${i + 1}`, slug: `s-${i + 1}`, status: 'published', access: 'free', hidden: false, excerpt: 'Boats.', picture: null })),
  cover_picture: null, hidden: false, published: [], created_at: '2026-10-21T09:00:00Z', updated_at: '2026-10-21T09:00:00Z', ...over,
})

describe('an issue edited on its pages', () => {
  const excerpts = new Map([[P1, 'Boats.'], [P2, null], [P3, 'Salt.']])
  it('takes the cover and contents words', () => {
    const d = docOf(issue())
    expect(applyIssueEdit(d, 'issue:lines.0.text', 'Low tide now', excerpts)!.cover.lines[0].text).toBe('Low tide now')
    expect(applyIssueEdit(d, 'issue:lines.0.sub', 'A morning\nwith the boats', excerpts)!.cover.lines[0].sub).toBe('A morning with the boats')
    expect(applyIssueEdit(d, 'issue:issue_line.text', 'No. 3, autumn', excerpts)!.cover.issue_line.text).toBe('No. 3, autumn')
    expect(applyIssueEdit(d, 'issue:contents.heading', '', excerpts)!.contents.heading).toBe('')
    expect(applyIssueEdit(d, 'issue:lines.4.text', 'x', excerpts)).toBeNull()
    expect(applyIssueEdit(d, 'issue:masthead.text', 'x', excerpts)).toBeNull()
  })

  it('gives a story its own contents line, unless it is the dek shown already', () => {
    const d = docOf(issue())
    expect(applyIssueEdit(d, `issue:line:${P1}`, 'Out with the boats', excerpts)!.stories[0].contents_line).toBe('Out with the boats')
    expect(applyIssueEdit(d, `issue:line:${P1}`, 'Boats.', excerpts)).toBe(d)
    expect(applyIssueEdit(d, `issue:line:${P1}`, '  ', excerpts)).toBe(d)
    expect(applyIssueEdit(d, 'issue:line:44444444-4444-4444-8444-444444444444', 'x', excerpts)).toBeNull()
  })

  it('renames a section for the run of stories under it', () => {
    const d = docOf(issue())
    const next = applyIssueEdit(d, `issue:section:${P1}`, 'Long reads', excerpts)!
    expect(next.stories.map((s) => s.section)).toEqual(['Long reads', 'Long reads', 'Dispatches'])
    expect(applyIssueEdit(d, `issue:section:${P3}`, '', excerpts)!.stories[2].section).toBeNull()
  })

  it('moves cover words and focuses the photo, as the server keeps them', () => {
    expect(moveCoverEl(cover, 'line:0', 10.04, 20, null)!.lines[0]).toMatchObject({ x: 10, y: 20, w: 60 })
    expect(moveCoverEl(cover, 'masthead', 50, 2, 80)!.masthead).toMatchObject({ x: 20, w: 80 })  // kept on the cover
    expect(moveCoverEl(cover, 'issue_line', 3, 4, null)!.issue_line).toMatchObject({ x: 3, y: 4 })
    expect(moveCoverEl(cover, 'line:3', 1, 1, null)).toBeNull()
    expect(coverFocal(cover, 33.4, 101).photo.focal).toEqual({ x: 33, y: 100 })
  })
})

// ── the frame ────────────────────────────────────────────────────────────────

describe('fitFrame', () => {
  it('lays a spread out at a reader’s window, made smaller to fit, never larger', () => {
    expect(fitFrame('spread', 0, 600)).toBeNull()
    const narrow = fitFrame('spread', 880, 838)!
    expect(narrow).toMatchObject({ width: SPREAD_MIN, left: 0, top: 0 })
    expect(narrow.scale).toBeCloseTo(880 / SPREAD_MIN)
    expect(narrow.height * narrow.scale).toBeCloseTo(838)
    expect(fitFrame('spread', 1500, 900)).toMatchObject({ width: 1500, height: 900, scale: 1 })
  })
  it('shows a phone whole, centred', () => {
    const big = fitFrame('phone', 1200, 1000)!
    expect(big).toMatchObject({ width: PHONE.width, height: PHONE.height, scale: 1 })
    expect(big.left).toBeCloseTo((1200 - PHONE.width - 12) / 2)
    const short = fitFrame('phone', 1200, 600)!
    expect(short.scale).toBeCloseTo((600 - 32) / (PHONE.height + 12))
  })
})

const send = (source: Window, data: unknown) =>
  act(() => { window.dispatchEvent(new MessageEvent('message', { data, source })) })
const frameWith = (html: string) => document.querySelector(`iframe[srcdoc="${html}"]`) as HTMLIFrameElement | null

describe('EditFrame', () => {
  it('shows a new render once it has turned to the place, and never while words are typed', async () => {
    const onMessage = vi.fn()
    const props = { place: { target: { kind: 'block', story: 'p-1', block: 2 } as const, spread: 3 }, stories: ctx.stories,
      device: 'spread' as const, title: 'Pages', onMessage }
    const { rerender } = render(<EditFrame html="<p>one</p>" {...props} />)
    const one = frameWith('<p>one</p>')!
    const toOne = vi.spyOn(one.contentWindow!, 'postMessage')
    send(one.contentWindow!, { type: 'mz-ready' })
    expect(toOne).toHaveBeenCalledWith({ type: 'mz-goto', target: props.place.target, spread: 3 }, '*')
    send(one.contentWindow!, { type: 'mz-shown' })
    expect(screen.getByTitle('Pages')).toBe(one)

    // Not the shown frame, or not well formed: not heard.
    send(window, { type: 'mz-select', target: { kind: 'none' } })
    send(one.contentWindow!, { type: 'mz-select', target: { kind: 'block', story: 'stranger', block: 1 } })
    expect(onMessage).not.toHaveBeenCalled()
    send(one.contentWindow!, { type: 'mz-select', target: { kind: 'contents' } })
    expect(onMessage).toHaveBeenCalledWith({ type: 'mz-select', target: { kind: 'contents' } })

    rerender(<EditFrame html="<p>two</p>" {...props} />)
    const two = frameWith('<p>two</p>')!
    expect(screen.getByTitle('Pages')).toBe(one)  // still the old one until the new one is ready
    send(two.contentWindow!, { type: 'mz-select', target: { kind: 'contents' } })
    expect(onMessage).toHaveBeenCalledTimes(1)  // the loading frame isn't listened to
    send(two.contentWindow!, { type: 'mz-ready' })
    send(two.contentWindow!, { type: 'mz-shown' })
    expect(screen.getByTitle('Pages')).toBe(two)

    // Typing on it: a new render waits.
    send(two.contentWindow!, { type: 'mz-editing', on: true })
    rerender(<EditFrame html="<p>three</p>" {...props} />)
    expect(frameWith('<p>three</p>')).toBeNull()
    send(two.contentWindow!, { type: 'mz-editing', on: false })
    await waitFor(() => expect(frameWith('<p>three</p>')).not.toBeNull())
    expect(onMessage).toHaveBeenCalledWith({ type: 'mz-editing', on: false })
  })

  it('selects on the page what is selected outside it', () => {
    const props = { stories: ctx.stories, device: 'phone' as const, title: 'Pages', onMessage: vi.fn() }
    const { rerender } = render(<EditFrame html="<p>one</p>" place={{ target: null, spread: 0 }} {...props} />)
    const one = frameWith('<p>one</p>')!
    send(one.contentWindow!, { type: 'mz-ready' })
    send(one.contentWindow!, { type: 'mz-shown' })
    const posted = vi.spyOn(one.contentWindow!, 'postMessage')
    rerender(<EditFrame html="<p>one</p>" place={{ target: { kind: 'contents' }, spread: 0 }} {...props} />)
    expect(posted).toHaveBeenCalledWith({ type: 'mz-select', target: { kind: 'contents' } }, '*')
  })
})

// ── the editors' pages ───────────────────────────────────────────────────────

function answer(routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path.endsWith(k))
    return hit === undefined ? Promise.reject(new Error(`unexpected GET ${path}`)) : Promise.resolve(routes[hit])
  })
}

const post = (over: Partial<CappePost> = {}): CappePost => ({
  id: 'p-1', site_id: 's-1', title: 'Low tide', slug: 'low-tide', excerpt: 'Boats.', body: 'x', cover_image_url: null,
  status: 'draft', published_at: null, created_at: '2026-10-20T09:00:00Z', updated_at: '2026-10-20T09:00:00Z', format: 'blocks',
  content: { blocks: [newBlock('cover'), text('First words.')] }, kicker: '', topic: '', layout: 'standard', access: 'free',
  cover_asset_id: null, byline: 'Ana', word_count: 2, reading_minutes: 1, hidden: false, ...over,
})

/** The page the editor sets: shown, as the frame would show it. */
async function shown(html: string) {
  const frame = await waitFor(() => { const f = frameWith(html); if (!f) throw new Error('not yet'); return f })
  const win = frame.contentWindow!
  const posted = vi.spyOn(win, 'postMessage')
  send(win, { type: 'mz-ready' })
  send(win, { type: 'mz-shown' })
  return { win, posted, say: (m: FrameMessage | Record<string, unknown>) => send(win, m) }
}

const editCalls = () => api.postHtml.mock.calls.filter(([, body]) => (body as { edit?: boolean }).edit).length

beforeEach(() => {
  vi.clearAllMocks()
  api.postHtml.mockImplementation((_path: string, body: { edit?: boolean }) =>
    Promise.resolve(body.edit ? `<p>edit ${editCalls()}</p>` : '<p>preview</p>'))
})

function mountStory() {
  answer({
    '/posts/p-1': post(),
    '/stories/options': { layouts: [], topics: [] },
    '/assets': { assets: [] },
    '/magazine': { paid_enabled: false },
  })
  return render(<MemoryRouter initialEntries={['/cappe/sites/s-1/stories/p-1']}><Routes>
    <Route path="/cappe/sites/:siteId/stories/:postId" element={<StoryEditor />} />
  </Routes></MemoryRouter>)
}

describe('StoryEditor, on the page', () => {
  it('types, formats, adds and undoes on the page, and saves what it shows', async () => {
    mountStory()
    const page = await shown('<p>edit 1</p>')
    expect(page.posted).toHaveBeenCalledWith({ type: 'mz-goto', target: null, spread: 0 }, '*')
    expect(api.postHtml).toHaveBeenCalledWith('/sites/s-1/stories/preview', expect.objectContaining({ edit: true, title: 'Low tide' }))
    expect(screen.getByText('The story')).toBeInTheDocument()

    // A block clicked: its settings, not its words.
    page.say({ type: 'mz-select', target: { kind: 'block', story: 'preview', block: 1 } })
    expect(await screen.findByRole('heading', { name: 'Text' })).toBeInTheDocument()
    expect(screen.getByText('Align')).toBeInTheDocument()
    expect(screen.queryByText('Columns')).toBeNull()  // a book page is already a column
    expect(screen.queryByLabelText('Text')).toBeNull()

    // Words typed: kept, and the page isn't set again while they're typed.
    const before = editCalls()
    page.say({ type: 'mz-editing', on: true })
    page.say({ type: 'mz-edit', story: 'preview', block: 1, field: 'caption', value: 'nope', rich: false })
    expect(screen.queryByText('Unsaved')).toBeNull()
    page.say({ type: 'mz-edit', story: 'preview', block: 1, field: 'md', value: doc(t('New '), t('words', 'bold')), rich: true })
    page.say({ type: 'mz-edit', story: 'preview', block: -1, field: '@title', value: 'High tide', rich: false })
    expect(await screen.findByText('Unsaved')).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 400))
    expect(editCalls()).toBe(before)
    page.say({ type: 'mz-editing', on: false })
    await waitFor(() => expect(editCalls()).toBe(before + 1))

    // A block added from the page, then undone from the page.
    page.say({ type: 'mz-insert', story: 'preview', at: 2, kind: 'quote' })
    expect(await screen.findByRole('heading', { name: 'Pull quote' })).toBeInTheDocument()
    page.say({ type: 'mz-key', key: 'undo' })
    expect(await screen.findByText('The story')).toBeInTheDocument()

    api.put.mockImplementation((_p: string, body: Record<string, unknown>) => Promise.resolve(post(body as Partial<CappePost>)))
    page.say({ type: 'mz-key', key: 'save' })
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const body = api.put.mock.calls[0][1]
    expect(body.title).toBe('High tide')
    expect(body.content.blocks).toHaveLength(2)
    expect(body.content.blocks[1]).toMatchObject({ type: 'text', md: 'New **words**', rt: doc(t('New '), t('words', 'bold')) })
  })

  it('asks for a picture where the page asks, and deletes the block selected', async () => {
    mountStory()
    const page = await shown('<p>edit 1</p>')
    page.say({ type: 'mz-pick', story: 'preview', block: 0, item: null })
    expect(await screen.findByRole('dialog', { name: 'Choose a picture' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close picker' }))
    page.say({ type: 'mz-select', target: { kind: 'block', story: 'preview', block: 1 } })
    await screen.findByRole('heading', { name: 'Text' })
    page.say({ type: 'mz-key', key: 'delete' })
    expect(await screen.findByText('The story')).toBeInTheDocument()
    expect(screen.getByText('Unsaved')).toBeInTheDocument()
  })

  it('opens the outline from the address, and switches between them', async () => {
    mountStory()
    await shown('<p>edit 1</p>')
    fireEvent.click(screen.getByRole('button', { name: 'Outline' }))
    expect(await screen.findByLabelText('Headline')).toHaveValue('Low tide')
    fireEvent.click(screen.getByRole('button', { name: 'Page' }))
    expect(screen.queryByLabelText('Headline')).toBeNull()
  })
})

const issueOptions: CappeMagazineIssueOptions = {
  templates: [{ key: 'classic', label: 'Classic', cover }], max_lines: 8, max_stories: 40, next_number: 4, taken: [],
}

function mountIssue() {
  answer({
    '/magazine/issues/i-1': issue({ stories: issue().stories.slice(0, 1) }),
    '/magazine/issues/options': issueOptions,
    '/posts': [post({ id: P1, status: 'published' })],
    '/assets': { assets: [] },
    '/magazine': { name: 'The Machine' },
  })
  return render(<MemoryRouter initialEntries={['/cappe/sites/s-1/issues/i-1']}><Routes>
    <Route path="/cappe/sites/:siteId/issues/:issueId" element={<IssueEditor />} />
  </Routes></MemoryRouter>)
}

describe('IssueEditor, on its pages', () => {
  it('edits the cover, the contents and a story in place, and saves the issue and the story', async () => {
    mountIssue()
    const page = await shown('<p>edit 1</p>')
    expect(screen.getByText('The issue')).toBeInTheDocument()

    page.say({ type: 'mz-select', target: { kind: 'cover', el: 'line:0' } })
    expect(await screen.findByRole('heading', { name: 'Cover line 1' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Cover line words')).toBeNull()  // typed on the cover
    page.say({ type: 'mz-edit', story: '', block: -1, field: 'issue:lines.0.text', value: 'Low tide now', rich: false })
    page.say({ type: 'mz-move', target: { kind: 'cover', el: 'line:0' }, x: 10, y: 20 })
    page.say({ type: 'mz-select', target: { kind: 'contents' } })
    expect(await screen.findByRole('heading', { name: 'Contents' })).toBeInTheDocument()
    page.say({ type: 'mz-edit', story: '', block: -1, field: `issue:line:${P1}`, value: 'Out with the boats', rich: false })
    page.say({ type: 'mz-edit', story: P1, block: 1, field: 'md', value: doc(t('Fresh '), t('words', 'italic')), rich: true })
    page.say({ type: 'mz-select', target: { kind: 'block', story: P1, block: 1 } })
    expect(await screen.findByText('In “Low tide”')).toBeInTheDocument()
    expect(await screen.findByText('Unsaved (and a story)')).toBeInTheDocument()

    // The page's next render carries the story's unsaved words.
    await waitFor(() => expect(api.postHtml).toHaveBeenLastCalledWith('/sites/s-1/magazine/issues/preview', expect.objectContaining({
      edit: true, stories_content: { [P1]: expect.objectContaining({ content: { blocks: [expect.anything(), expect.objectContaining({ md: 'Fresh *words*' })] } }) },
    })))

    api.put.mockImplementation((path: string, body: Record<string, unknown>) => Promise.resolve(path.includes('/posts/')
      ? post({ id: P1, status: 'published', ...(body as Partial<CappePost>) })
      : issue({ stories: issue().stories.slice(0, 1), cover: body.cover as CoverDesign })))
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    const [issuePut, storyPut] = api.put.mock.calls
    expect(issuePut[0]).toBe('/sites/s-1/magazine/issues/i-1')
    expect(issuePut[1].cover.lines[0]).toMatchObject({ text: 'Low tide now', x: 10, y: 20 })
    expect(issuePut[1].stories[0]).toMatchObject({ contents_line: 'Out with the boats' })
    expect(storyPut[0]).toBe(`/sites/s-1/posts/${P1}`)
    expect(storyPut[1]).toMatchObject({ title: 'Low tide', content: { blocks: [expect.anything(), expect.objectContaining({ md: 'Fresh *words*' })] } })
    expect(storyPut[1]).not.toHaveProperty('status')
    await waitFor(() => expect(screen.queryByText(/Unsaved/)).toBeNull())
  })

  it('names a story it could not save and keeps its words', async () => {
    mountIssue()
    const page = await shown('<p>edit 1</p>')
    page.say({ type: 'mz-edit', story: P1, block: -1, field: '@title', value: 'Lower tide', rich: false })
    await screen.findByText('Unsaved (and a story)')
    api.put.mockRejectedValue(new Error('That picture is not in your library.'))
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Not saved: “Lower tide” (That picture is not in your library.)')
    expect(api.put).toHaveBeenCalledTimes(1)  // the issue itself was unchanged
    expect(screen.getByText('Unsaved (and a story)')).toBeInTheDocument()
  })
})
