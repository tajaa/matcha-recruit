import type { Node as PMNode } from '@tiptap/pm/model'
import type { Transaction } from '@tiptap/pm/state'
import type { EditorProps } from '@tiptap/pm/view'

export const BODY_WRITING_NOTICE = 'Write article bodies directly here. Pasting and dropping text are disabled.'

/** Guard the editor's insertion paths, rather than keyboard shortcuts, so
 *  context menus and mobile paste obey the same rule. Typing, IME, spelling
 *  corrections and undo keep their ordinary behavior. */
export function bodyWritingProps(isBody: (paragraph: PMNode) => boolean, blocked: () => void): EditorProps {
  const bodyIn = (doc: PMNode, from: number, to: number): boolean => {
    let found = false
    const parent = doc.resolve(from).parent
    if (parent.isTextblock && isBody(parent)) return true
    doc.nodesBetween(from, to, (node) => {
      if (node.isTextblock && isBody(node)) found = true
      return !found
    })
    return found
  }
  const changesBody = (tr: Transaction): boolean => tr.steps.some((step, i) => {
    let found = false
    const before = tr.docs[i], after = tr.docs[i + 1] ?? tr.doc
    step.getMap().forEach((a, b, c, d) => {
      if (bodyIn(before, a, b) || bodyIn(after, c, d)) found = true
    })
    return found
  })
  const reject = (event: Event): true => {
    event.preventDefault()
    blocked()
    return true
  }
  return {
    handleDOMEvents: {
      paste: (view, event) => {
        const { doc, selection } = view.state
        return bodyIn(doc, selection.from, selection.to) ? reject(event) : false
      },
      beforeinput: (view, event) => {
        if (!/^insertFrom(?:Paste|Drop)/.test(event.inputType)) return false
        const { doc, selection } = view.state
        return bodyIn(doc, selection.from, selection.to) ? reject(event) : false
      },
    },
    handlePaste: (view, event, slice) => changesBody(view.state.tr.replaceSelection(slice)) ? reject(event) : false,
    handleDrop: (view, event, slice, moved) => {
      const { doc, selection } = view.state
      if (moved && bodyIn(doc, selection.from, selection.to)) return reject(event)
      const at = view.posAtCoords({ left: event.clientX, top: event.clientY })
      if (!at) return false
      return bodyIn(doc, at.pos, at.pos) || changesBody(view.state.tr.replaceRange(at.pos, at.pos, slice))
        ? reject(event) : false
    },
  }
}
