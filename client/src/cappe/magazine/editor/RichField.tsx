import { useEffect, useState } from 'react'
import { EditorContent, useEditor, type Editor } from '@tiptap/react'
import { Bold, Heading2, Heading3, Italic, Link2, List, ListOrdered, Quote, Strikethrough, Underline } from 'lucide-react'
import { ui } from '../../components/ui'
import { cleanRt, emptyRt, richPatch, type RtDoc } from '../canvas/rt'
import { richExtensions } from '../frame/extensions'

type Tool = { key: string; label: string; icon: typeof Bold; run: (e: Editor) => void; on: (e: Editor) => boolean }

const TOOLS: Tool[] = [
  { key: 'bold', label: 'Bold (⌘B)', icon: Bold, run: (e) => e.chain().focus().toggleBold().run(), on: (e) => e.isActive('bold') },
  { key: 'italic', label: 'Italic (⌘I)', icon: Italic, run: (e) => e.chain().focus().toggleItalic().run(), on: (e) => e.isActive('italic') },
  { key: 'underline', label: 'Underline (⌘U)', icon: Underline, run: (e) => e.chain().focus().toggleUnderline().run(), on: (e) => e.isActive('underline') },
  { key: 'strike', label: 'Strike through', icon: Strikethrough, run: (e) => e.chain().focus().toggleStrike().run(), on: (e) => e.isActive('strike') },
  { key: 'h2', label: 'Heading', icon: Heading2, run: (e) => e.chain().focus().toggleHeading({ level: 2 }).run(), on: (e) => e.isActive('heading', { level: 2 }) },
  { key: 'h3', label: 'Small heading', icon: Heading3, run: (e) => e.chain().focus().toggleHeading({ level: 3 }).run(), on: (e) => e.isActive('heading', { level: 3 }) },
  { key: 'quote', label: 'Quote', icon: Quote, run: (e) => e.chain().focus().toggleBlockquote().run(), on: (e) => e.isActive('blockquote') },
  { key: 'bullets', label: 'Bulleted list', icon: List, run: (e) => e.chain().focus().toggleBulletList().run(), on: (e) => e.isActive('bulletList') },
  { key: 'numbers', label: 'Numbered list', icon: ListOrdered, run: (e) => e.chain().focus().toggleOrderedList().run(), on: (e) => e.isActive('orderedList') },
]

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/** Rich text in the Outline: the same editor, schema and document as typing
 *  on the page (frame/), with a formatting bar. */
export default function RichField({ value, onChange, label, placeholder = '', max, minHeight = '8rem' }: {
  value: RtDoc | undefined
  onChange: (patch: { rt: RtDoc; md: string }) => void
  label: string
  placeholder?: string
  /** The field's length, as the server keeps it. */
  max: number
  minHeight?: string
}) {
  const [link, setLink] = useState<string | null>(null)
  const editor = useEditor({
    extensions: richExtensions(placeholder),
    content: value ?? emptyRt(),
    shouldRerenderOnTransaction: true,
    editorProps: {
      attributes: {
        role: 'textbox', 'aria-multiline': 'true', 'aria-label': label,
        class: 'mz-rich-field prose prose-invert prose-sm max-w-none px-3 py-2 text-zinc-100 outline-none',
        style: `min-height:${minHeight}`,
      },
    },
    onUpdate: ({ editor: e }) => onChange(richPatch(e.getJSON(), max)),
  })

  // Changed from outside (undo, Assist): show it, without reporting it back.
  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    const next = value ?? emptyRt()
    if (!same(cleanRt(editor.getJSON(), max), next)) editor.commands.setContent(next, { emitUpdate: false })
  }, [editor, value, max])

  const applyLink = () => {
    if (!editor || link === null) return
    const raw = link.trim()
    const href = !raw || /^(https?:|mailto:)/i.test(raw) ? raw : `https://${raw}`
    const chain = editor.chain().focus().extendMarkRange('link')
    if (href) chain.setLink({ href }).run()
    else chain.unsetLink().run()
    setLink(null)
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 focus-within:border-emerald-500">
      <div className="flex flex-wrap items-center gap-0.5 border-b border-zinc-800 px-1.5 py-1" role="toolbar" aria-label={`Format ${label.toLowerCase()}`}>
        {TOOLS.map(({ key, label: name, icon: Icon, run, on }) => (
          <button key={key} type="button" title={name} aria-label={name} aria-pressed={!!editor && on(editor)}
            // Keep the selection in the field while the button is pressed.
            onMouseDown={(e) => e.preventDefault()} onClick={() => editor && run(editor)}
            className={`rounded p-1.5 hover:bg-zinc-800 hover:text-zinc-100 ${editor && on(editor) ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-400'}`}>
            <Icon className="h-4 w-4" />
          </button>
        ))}
        <button type="button" title="Link (⌘K)" aria-label="Link" aria-pressed={!!editor?.isActive('link')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => setLink((editor?.getAttributes('link').href as string | undefined) || '')}
          className={`rounded p-1.5 hover:bg-zinc-800 hover:text-zinc-100 ${editor?.isActive('link') ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-400'}`}>
          <Link2 className="h-4 w-4" />
        </button>
        {link !== null && (
          <input autoFocus value={link} onChange={(e) => setLink(e.target.value)} aria-label="Link address" placeholder="Paste a link, then Enter"
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); applyLink() }
              if (e.key === 'Escape') { e.preventDefault(); setLink(null); editor?.commands.focus() }
            }}
            className={`${ui.input} ml-1 h-7 min-w-0 flex-1 py-0 text-xs`} />
        )}
      </div>
      <EditorContent editor={editor}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault()
            setLink((editor?.getAttributes('link').href as string | undefined) || '')
          }
        }} />
    </div>
  )
}
