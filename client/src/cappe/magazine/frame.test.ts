import type { Editor } from '@tiptap/core'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

/** The editor that runs inside a page being edited (frame/), loaded onto a
 *  small edit render: what it sends the editor outside for clicks, typing
 *  and keys, and what it does when told where to turn. */

const PAGE = `
<div class="mz-reader" data-mz-edit><div class="mz-book"><div class="mz-pages">
  <article class="mz-story" data-mz-s="p1">
    <h1 class="mz-headline" data-mz-f="@title" data-mz-k="plain" data-mz-ph="Headline">Low tide</h1>
    <div class="mz-story__body">
      <div class="mz-text" data-mz-b="1" data-mz-f="md" data-mz-k="rich" data-mz-ph="Write here"><p>old words</p></div>
      <figure class="mz-photo" data-mz-b="2"><div data-mz-pick data-mz-item="0">Choose a picture</div>
        <figcaption data-mz-f="caption" data-mz-k="plain" data-mz-ph="Caption"></figcaption></figure>
      <div class="mz-text" data-mz-b="3" data-mz-f="md" data-mz-k="rich" data-mz-ph="Write here"></div>
    </div>
    <script type="application/json" data-mz-rt>{"1|md":{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"From the registry"}]}]}}</script>
  </article>
</div></div></div>`

type Sent = Record<string, unknown> & { type: string }
const sent: Sent[] = []
// Plain functions, not mocks: the config resets mocks between tests, and
// the page is loaded once for all of them.
const calls: [string, ...unknown[]][] = []
const book = {
  go: (spread: number, now?: boolean) => { calls.push(['go', spread, now]) },
  at: () => 0,
  spreadOf: () => 1,
  refit: () => { calls.push(['refit']) },
}
const wait = (ms = 300) => new Promise((r) => setTimeout(r, ms))
const lastOf = (type: string) => sent.filter((m) => m.type === type).at(-1)
const field = (sel: string) => document.querySelector(sel) as HTMLElement & { editor?: Editor }
const key = (k: string, over: KeyboardEventInit = {}) =>
  document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...over }))

beforeAll(async () => {
  document.body.innerHTML = PAGE
  window.mzBook = book
  window.postMessage = ((m: Sent) => { sent.push(m) }) as typeof window.postMessage
  // jsdom lays nothing out.
  Element.prototype.scrollIntoView = () => {}
  Range.prototype.getBoundingClientRect = () => new DOMRect(10, 10, 20, 10)
  Range.prototype.getClientRects = () => [new DOMRect(10, 10, 20, 10)] as unknown as DOMRectList
  await import('./frame/index')
})

afterAll(() => { document.body.innerHTML = ''; delete window.mzBook })

describe('the editor on the page', () => {
  it('opens each rich field from its document and says it is ready', () => {
    expect(sent.map((m) => m.type)).toContain('mz-ready')
    const words = field('[data-mz-b="1"]')
    expect(words.classList.contains('ProseMirror')).toBe(true)
    expect(words.textContent).toBe('From the registry')  // the document, not the page's HTML
    expect(field('[data-mz-b="3"] p')?.getAttribute('data-placeholder')).toBe('Write here')
    expect(field('h1').getAttribute('contenteditable')).toMatch(/plaintext-only|true/)
  })

  it('turns to the place it is told, once, and shows the page', async () => {
    window.dispatchEvent(new MessageEvent('message', { source: window, data: { type: 'mz-goto', target: { kind: 'block', story: 'p1', block: 2 }, spread: 0 } }))
    await wait(50)
    expect(calls).toContainEqual(['refit'])
    expect(calls).toContainEqual(['go', 1, true])
    expect(document.querySelector('[data-mz-edit]')!.classList.contains('mze-on')).toBe(true)
    expect(sent.filter((m) => m.type === 'mz-shown')).toHaveLength(1)
    expect(field('[data-mz-b="2"]').classList.contains('mze-sel')).toBe(true)
    // A message from anywhere but the editor outside is ignored.
    window.dispatchEvent(new MessageEvent('message', { source: null, data: { type: 'mz-select', target: { kind: 'none' } } }))
    expect(field('[data-mz-b="2"]').classList.contains('mze-sel')).toBe(true)
  })

  it('says what a click lands on, and asks for a picture', () => {
    field('[data-mz-b="1"] p').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(lastOf('mz-select')).toEqual({ type: 'mz-select', target: { kind: 'block', story: 'p1', block: 1 } })
    field('[data-mz-pick]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(lastOf('mz-pick')).toEqual({ type: 'mz-pick', story: 'p1', block: 2, item: 0 })
    field('h1').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(lastOf('mz-select')).toEqual({ type: 'mz-select', target: { kind: 'story', story: 'p1' } })
  })

  it('sends plain words as typed, and Enter ends them', async () => {
    const h1 = field('h1')
    h1.focus()
    expect(lastOf('mz-editing')).toEqual({ type: 'mz-editing', on: true })
    h1.textContent = 'Low tide today'
    h1.dispatchEvent(new Event('input', { bubbles: true }))
    await wait()
    expect(lastOf('mz-edit')).toEqual({ type: 'mz-edit', story: 'p1', block: -1, field: '@title', value: 'Low tide today', rich: false })
    key('Enter')
    await wait(20)
    expect(document.activeElement).not.toBe(h1)
    expect(lastOf('mz-editing')).toEqual({ type: 'mz-editing', on: false })
  })

  it('puts a headline back on Escape', async () => {
    const h1 = field('h1')
    h1.focus()
    h1.textContent = 'A slip'
    key('Escape')
    await wait(20)
    expect(h1.textContent).toBe('Low tide today')
  })

  it('sends a rich field as its document', async () => {
    const words = field('[data-mz-b="1"]')
    words.editor!.commands.focus('end')
    words.editor!.commands.insertContent(' and more')
    await wait()
    expect(lastOf('mz-edit')).toEqual({
      type: 'mz-edit', story: 'p1', block: 1, field: 'md', rich: true,
      value: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'From the registry and more' }] }] },
    })
    // Format from the bar over the selection.
    words.editor!.commands.setTextSelection({ from: 1, to: 5 })
    document.dispatchEvent(new Event('selectionchange'))
    const bold = document.querySelector('.mze-bar button[data-cmd="bold"]') as HTMLButtonElement
    bold.click()
    await wait()
    const value = lastOf('mz-edit')!.value as { content: { content: { text: string; marks?: unknown[] }[] }[] }
    expect(value.content[0].content[0]).toEqual({ type: 'text', text: 'From', marks: [{ type: 'bold' }] })
    // A link typed into the bar (⌘K).
    words.editor!.commands.setTextSelection({ from: 6, to: 9 })
    key('k', { metaKey: true })
    const box = document.querySelector('.mze-link') as HTMLInputElement
    expect(box.hidden).toBe(false)
    box.value = 'example.com'
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await wait()
    const linked = lastOf('mz-edit')!.value as { content: { content: { text: string; marks?: unknown[] }[] }[] }
    expect(linked.content[0].content.find((n) => n.text === 'the')?.marks).toEqual([{ type: 'link', attrs: { href: 'https://example.com' } }])
    expect(box.hidden).toBe(true)
    // ⌘S sends the words, then asks to save.
    key('s', { metaKey: true })
    expect(sent.at(-1)).toEqual({ type: 'mz-key', key: 'save' })
  })

  it('hands undo, redo, save and delete to the editor outside when not typing', async () => {
    words().editor!.commands.blur()
    await wait(50)
    ;(document.activeElement as HTMLElement | null)?.blur()
    field('[data-mz-b="2"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const keys = () => sent.filter((m) => m.type === 'mz-key').map((m) => m.key)
    const before = keys().length
    for (const [k, over] of [['z', { metaKey: true }], ['z', { metaKey: true, shiftKey: true }], ['y', { ctrlKey: true }], ['s', { metaKey: true }], ['Backspace', {}]] as const) {
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...over }))
    }
    expect(keys().slice(before)).toEqual(['undo', 'redo', 'redo', 'save', 'delete'])
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(lastOf('mz-select')).toEqual({ type: 'mz-select', target: { kind: 'none' } })
  })

  it('adds a block after the one under the pointer', () => {
    field('[data-mz-b="2"]').dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    ;(document.querySelector('.mze-plus') as HTMLButtonElement).click()
    ;(document.querySelector('.mze-menu button[data-type="divider"]') as HTMLButtonElement).click()
    expect(lastOf('mz-insert')).toEqual({ type: 'mz-insert', story: 'p1', at: 3, kind: 'divider' })
  })
})

const words = () => field('[data-mz-b="1"]')
