import { useEffect, useRef, useCallback } from 'react'
import { useEditor } from '@tiptap/react'
import { Extension, Node, mergeAttributes } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import LinkExtension from '@tiptap/extension-link'
import ImageExtension from '@tiptap/extension-image'
import { avatarColor } from '../../utils/avatarColor'
import type { PresenceMember } from '../../api/projectSocket'
import type { RemoteCaret } from '../../hooks/useProjectPresence'

/** Block-level <video> node so insertContent('<video ...>') survives TipTap
 * serialization. StarterKit has no video node — without this, the tag is
 * stripped on the next getHTML() and the upload silently disappears. */
const VideoNode = Node.create({
  name: 'video',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,
  addAttributes() {
    return {
      src: { default: null },
      poster: { default: null },
      controls: { default: true },
      width: { default: '600' },
    }
  },
  parseHTML() {
    return [{ tag: 'video' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['video', mergeAttributes(HTMLAttributes)]
  },
})

/** Plugin key for the remote-caret decorations. The SectionEditor component
 * dispatches a transaction with `tr.setMeta(remoteCaretPluginKey, set)`
 * whenever the `remoteCarets` map updates; the plugin renders that
 * DecorationSet (caret bars + selection highlights for collaborators on the
 * same section). Doc edits between dispatches still re-map positions via
 * `old.map(tr.mapping, tr.doc)` so the markers stay aligned. */
const remoteCaretPluginKey = new PluginKey('remoteCaret')

const RemoteCaretExtension = Extension.create({
  name: 'remoteCaret',
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: remoteCaretPluginKey,
        state: {
          init: () => DecorationSet.empty,
          apply(tr, old) {
            const incoming = tr.getMeta(remoteCaretPluginKey)
            if (incoming) return incoming as DecorationSet
            return (old as DecorationSet).map(tr.mapping, tr.doc)
          },
        },
        props: {
          decorations(state) {
            return remoteCaretPluginKey.getState(state) as DecorationSet
          },
        },
      }),
    ]
  },
})

/** TipTap extension that highlights [bracketed placeholders] with orange styling */
const PlaceholderHighlight = Extension.create({
  name: 'placeholderHighlight',
  addProseMirrorPlugins() {
    function findPlaceholders(doc: Parameters<typeof DecorationSet.create>[0]) {
      const decos: Decoration[] = []
      doc.descendants((node, pos) => {
        if (node.isText && node.text) {
          const regex = /\[[^\]]+\]/g
          let match
          while ((match = regex.exec(node.text)) !== null) {
            decos.push(
              Decoration.inline(pos + match.index, pos + match.index + match[0].length, {
                class: 'bracket-placeholder',
              })
            )
          }
        }
      })
      return DecorationSet.create(doc, decos)
    }
    return [
      new Plugin({
        key: new PluginKey('placeholderHighlight'),
        state: {
          init(_, { doc }) { return findPlaceholders(doc) },
          apply(tr, old) { return tr.docChanged ? findPlaceholders(tr.doc) : old },
        },
        props: {
          decorations(state) { return this.getState(state) },
        },
      }),
    ]
  },
})

export interface SectionEditorProps {
  content: string
  onUpdate: (html: string) => void
  onImageUpload?: (file: File) => Promise<string | null>
  onVideoUpload?: (file: File) => Promise<string | null>
  uploadingImage?: boolean
  uploadingVideo?: boolean
  // Real-time collaboration (optional — when omitted, editor behaves as before)
  sectionId?: string
  selfId?: string
  members?: PresenceMember[]
  remoteCarets?: Map<string, RemoteCaret>
  onCaretChange?: (sectionId: string, anchor: number, head: number) => void
}

export function useSectionEditor({
  content,
  onUpdate,
  onImageUpload,
  onVideoUpload,
  sectionId,
  selfId,
  members,
  remoteCarets,
  onCaretChange,
}: SectionEditorProps) {
  const imageInputRef = useRef<HTMLInputElement>(null)
  const videoInputRef = useRef<HTMLInputElement>(null)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
      }),
      Placeholder.configure({ placeholder: 'Start typing...' }),
      LinkExtension.configure({ openOnClick: false }),
      ImageExtension,
      VideoNode,
      PlaceholderHighlight,
      RemoteCaretExtension,
    ],
    content,
    onUpdate: ({ editor: e }) => {
      const html = e.getHTML()
      lastServerContent.current = html
      onUpdate(html)
    },
    onSelectionUpdate: ({ editor: e }) => {
      if (!onCaretChange || !sectionId) return
      const { from, to } = e.state.selection
      onCaretChange(sectionId, from, to)
    },
    editorProps: {
      attributes: {
        class: 'outline-none min-h-[60px] px-3 py-2 text-xs leading-relaxed',
        style: 'color: #d4d4d4; font-family: -apple-system, BlinkMacSystemFont, sans-serif;',
      },
      handlePaste: (_view, event) => {
        const items = event.clipboardData?.items
        if (!items) return false
        for (const item of items) {
          if (item.type.startsWith('image/') && onImageUpload) {
            event.preventDefault()
            const file = item.getAsFile()
            if (file) {
              onImageUpload(file).then((url) => {
                if (url && editor) {
                  editor.chain().focus().setImage({ src: url }).run()
                }
              })
            }
            return true
          }
        }
        return false
      },
    },
  })

  // Sync content from server when the prop changes (e.g., placeholder replacement, new section from chat)
  const lastServerContent = useRef(content)
  useEffect(() => {
    if (editor && content !== lastServerContent.current) {
      lastServerContent.current = content
      if (content !== '<p></p>' && content !== editor.getHTML()) {
        editor.commands.setContent(content, { emitUpdate: false })
      }
    }
  }, [content, editor])

  // Push remote-caret decorations into the editor whenever the carets map,
  // members list, or active section changes.
  useEffect(() => {
    if (!editor || !remoteCarets || !sectionId) return
    const decos: Decoration[] = []
    const docSize = editor.state.doc.content.size
    const memberById = new Map((members ?? []).map((m) => [m.id, m]))
    for (const [userId, caret] of remoteCarets.entries()) {
      if (userId === selfId) continue
      if (caret.sectionId !== sectionId) continue
      const member = memberById.get(userId)
      if (!member) continue
      const color = avatarColor(userId)
      const from = Math.max(0, Math.min(Math.min(caret.anchor, caret.head), docSize))
      const to = Math.max(from, Math.min(Math.max(caret.anchor, caret.head), docSize))
      if (to > from) {
        decos.push(
          Decoration.inline(from, to, {
            style: `background-color: ${color}33;`,
          })
        )
      }
      const head = Math.max(0, Math.min(caret.head, docSize))
      const widget = document.createElement('span')
      widget.className = 'remote-caret'
      widget.style.cssText = `position: relative; display: inline-block; width: 0; height: 1em; vertical-align: text-bottom; border-left: 2px solid ${color};`
      const flag = document.createElement('span')
      flag.textContent = member.name
      flag.style.cssText = `position: absolute; top: -14px; left: -1px; background: ${color}; color: #000; font-size: 9px; font-weight: 600; padding: 1px 4px; border-radius: 2px; white-space: nowrap; pointer-events: none;`
      widget.appendChild(flag)
      decos.push(Decoration.widget(head, widget, { side: 1 }))
    }
    const set = DecorationSet.create(editor.state.doc, decos)
    const tr = editor.state.tr.setMeta(remoteCaretPluginKey, set)
    editor.view.dispatch(tr)
  }, [editor, remoteCarets, members, sectionId, selfId])

  const handleImageClick = useCallback(async () => {
    imageInputRef.current?.click()
  }, [])

  const handleImageFile = useCallback(async (file: File) => {
    if (!onImageUpload || !editor) return
    const url = await onImageUpload(file)
    if (url) {
      editor.chain().focus().setImage({ src: url }).run()
    }
  }, [onImageUpload, editor])

  const handleVideoClick = useCallback(() => {
    videoInputRef.current?.click()
  }, [])

  const handleVideoFile = useCallback(async (file: File) => {
    if (!onVideoUpload || !editor) return
    const url = await onVideoUpload(file)
    if (url) {
      // Insert via the registered VideoNode so the tag survives TipTap's
      // serialization round-trip. The email render path later swaps this
      // for a Gmail/Outlook-safe poster fallback.
      editor.chain().focus().insertContent({
        type: 'video',
        attrs: { src: url, controls: true, width: '600' },
      }).run()
    }
  }, [onVideoUpload, editor])

  return {
    editor,
    imageInputRef,
    videoInputRef,
    handleImageClick,
    handleImageFile,
    handleVideoClick,
    handleVideoFile,
  }
}
