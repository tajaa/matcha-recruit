import { useEffect, useRef, useCallback } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import LinkExtension from '@tiptap/extension-link'
import ImageExtension from '@tiptap/extension-image'
import { Bold, Italic, Heading2, List, ListOrdered, Link, ImagePlus, Loader2, Undo, Redo } from 'lucide-react'

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

interface SectionEditorProps {
  content: string
  onUpdate: (html: string) => void
  onImageUpload?: (file: File) => Promise<string | null>
  uploadingImage?: boolean
}

export default function SectionEditor({ content, onUpdate, onImageUpload, uploadingImage }: SectionEditorProps) {
  const imageInputRef = useRef<HTMLInputElement>(null)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
      }),
      Placeholder.configure({ placeholder: 'Start typing...' }),
      LinkExtension.configure({ openOnClick: false }),
      ImageExtension,
      PlaceholderHighlight,
    ],
    content,
    onUpdate: ({ editor: e }) => {
      const html = e.getHTML()
      lastServerContent.current = html
      onUpdate(html)
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

  if (!editor) return null

  const tb = (active: boolean) => ({
    color: active ? '#ce9178' : '#6a737d',
    background: active ? '#2a2d2e' : 'transparent',
  })

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-3 py-1" style={{ borderBottom: '1px solid #333' }}>
        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleBold().run() }}
          className="p-1 rounded transition-colors"
          style={tb(editor.isActive('bold'))}
          title="Bold"
        ><Bold size={13} /></button>
        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleItalic().run() }}
          className="p-1 rounded transition-colors"
          style={tb(editor.isActive('italic'))}
          title="Italic"
        ><Italic size={13} /></button>
        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleHeading({ level: 2 }).run() }}
          className="p-1 rounded transition-colors"
          style={tb(editor.isActive('heading', { level: 2 }))}
          title="Heading"
        ><Heading2 size={13} /></button>
        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleBulletList().run() }}
          className="p-1 rounded transition-colors"
          style={tb(editor.isActive('bulletList'))}
          title="Bullet list"
        ><List size={13} /></button>
        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleOrderedList().run() }}
          className="p-1 rounded transition-colors"
          style={tb(editor.isActive('orderedList'))}
          title="Numbered list"
        ><ListOrdered size={13} /></button>
        <button
          onMouseDown={(e) => {
            e.preventDefault()
            const url = window.prompt('URL:')
            if (url) editor.chain().focus().setLink({ href: url }).run()
          }}
          className="p-1 rounded transition-colors"
          style={tb(editor.isActive('link'))}
          title="Link"
        ><Link size={13} /></button>

        <div className="w-px h-3 mx-1" style={{ background: '#333' }} />

        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) handleImageFile(f)
            e.target.value = ''
          }}
        />
        <button
          onMouseDown={(e) => { e.preventDefault(); handleImageClick() }}
          className="p-1 rounded transition-colors"
          style={{ color: uploadingImage ? '#ce9178' : '#6a737d' }}
          title="Insert image"
        >
          {uploadingImage ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}
        </button>

        <div className="w-px h-3 mx-1" style={{ background: '#333' }} />

        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().undo().run() }}
          disabled={!editor.can().undo()}
          className="p-1 rounded transition-colors disabled:opacity-30"
          style={{ color: '#6a737d' }}
          title="Undo"
        ><Undo size={13} /></button>
        <button
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().redo().run() }}
          disabled={!editor.can().redo()}
          className="p-1 rounded transition-colors disabled:opacity-30"
          style={{ color: '#6a737d' }}
          title="Redo"
        ><Redo size={13} /></button>
      </div>

      {/* Editor */}
      <EditorContent editor={editor} />

      {/* TipTap dark theme styles */}
      <style>{`
        .tiptap {
          color: #d4d4d4;
          font-size: 12px;
          line-height: 1.65;
        }
        .tiptap p { margin: 4px 0; }
        .tiptap h2 { color: #e8e8e8; font-size: 15px; font-weight: 600; margin: 12px 0 6px; }
        .tiptap h3 { color: #e8e8e8; font-size: 13px; font-weight: 600; margin: 10px 0 4px; }
        .tiptap strong { color: #dcdcaa; }
        .tiptap em { color: #9cdcfe; }
        .tiptap ul, .tiptap ol { padding-left: 20px; margin: 4px 0; }
        .tiptap li { margin: 2px 0; }
        .tiptap a { color: #ce9178; text-decoration: underline; }
        .tiptap code { color: #ce9178; background: #2a2d2e; padding: 1px 4px; border-radius: 3px; font-family: ui-monospace, monospace; font-size: 11px; }
        .tiptap pre { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; padding: 8px; margin: 8px 0; }
        .tiptap img { max-width: 100%; border-radius: 4px; margin: 8px 0; }
        .tiptap p.is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          color: #6a737d;
          float: left;
          height: 0;
          pointer-events: none;
        }
        .bracket-placeholder {
          color: #f59e0b;
          background: rgba(245, 158, 11, 0.12);
          border-radius: 2px;
          padding: 0 1px;
        }
      `}</style>
    </div>
  )
}
