import { Editor, type JSONContent } from '@tiptap/core'
import { cleanRt, type RtDoc } from '../canvas/rt'
import { richExtensions } from './extensions'
import { blockOf } from './targets'

/** Fields of rich text (a text block, a sidebar, an interview's answers):
 *  each is a Tiptap editor mounted on the field itself, so the page keeps
 *  its own type, columns and drop cap while it is typed into. It opens the
 *  field's document exactly as saved, from the story's registry the edit
 *  render prints (`<script type="application/json" data-mz-rt>`, keyed
 *  `"<block>|<field>"`), never by reading the page's HTML back. */

const editors = new WeakMap<Element, Editor>()
const registries = new WeakMap<Element, Record<string, JSONContent>>()

export const editorOf = (f: Element): Editor | undefined => editors.get(f)

function registry(f: Element): Record<string, JSONContent> {
  const story = f.closest('[data-mz-s]')
  if (!story) return {}
  return storyRegistry(story)
}

function storyRegistry(story: Element): Record<string, JSONContent> {
  let reg = registries.get(story)
  if (!reg) {
    const json = story.querySelector(':scope > script[data-mz-rt]')?.textContent
    try { reg = json ? JSON.parse(json) as Record<string, JSONContent> : {} } catch { reg = {} }
    registries.set(story, reg ?? {})
  }
  return reg ?? {}
}

/** A field's document as it is now (a design drawn again from the editor
 *  outside): its field opens with these words, not the ones first printed. */
export function rememberRich(story: Element, key: string, doc: JSONContent) {
  storyRegistry(story)[key] = doc
}

export function makeRich(f: HTMLElement, onUpdate: (f: HTMLElement) => void, onSelection: () => void): Editor {
  const doc = registry(f)[`${blockOf(f)}|${f.getAttribute('data-mz-f')}`]
  const content: JSONContent | string = doc ?? f.innerHTML
  f.innerHTML = ''
  const editor = new Editor({
    element: { mount: f },
    extensions: richExtensions(f.getAttribute('data-mz-ph') || ''),
    content,
    editorProps: {
      attributes: { spellcheck: 'true' },
      // The book turns to the words being typed (typing.ts); the editor
      // scrolling the book itself would leave it between two pages.
      handleScrollToSelection: () => true,
    },
    onUpdate: () => onUpdate(f),
    onSelectionUpdate: onSelection,
  })
  editors.set(f, editor)
  return editor
}

/** What a rich field holds now, as the server keeps it. */
export const richValue = (f: Element): RtDoc | null => {
  const ed = editors.get(f)
  return ed ? cleanRt(ed.getJSON()) : null
}
