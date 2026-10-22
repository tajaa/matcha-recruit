import type { AnyExtension } from '@tiptap/core'
import Placeholder from '@tiptap/extension-placeholder'
import StarterKit from '@tiptap/starter-kit'
import { cleanHref } from '../canvas/rt'

/** What a story's rich text can hold, for every editor that types it (the
 *  page's, the Outline's): paragraphs, two levels of heading, quotes, lists,
 *  line breaks; bold, italic, underline, strike-through and links (web and
 *  mail addresses only). The server keeps exactly this (services/magazine/
 *  rt.py); anything else pasted in becomes plain paragraphs. */
export function richExtensions(placeholder = ''): AnyExtension[] {
  return [
    StarterKit.configure({
      heading: { levels: [2, 3] },
      code: false,
      codeBlock: false,
      horizontalRule: false,
      // No empty paragraph added after a list or a quote: the page prints none.
      trailingNode: false,
      link: {
        openOnClick: false,
        autolink: true,
        linkOnPaste: true,
        defaultProtocol: 'https',
        HTMLAttributes: { rel: 'nofollow ugc noopener', target: null },
        isAllowedUri: (url) => !!cleanHref(url),
      },
    }),
    Placeholder.configure({ placeholder }),
  ]
}
