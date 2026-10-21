import { useRef } from 'react'
import { Bold, Heading2, Heading3, Italic, Link2, List, ListOrdered, Quote } from 'lucide-react'
import { formatMarkdown, shortcutFormat, type MdFormat } from './markdown'

const TOOLS: { kind: MdFormat; label: string; icon: typeof Bold }[] = [
  { kind: 'bold', label: 'Bold (⌘B)', icon: Bold },
  { kind: 'italic', label: 'Italic (⌘I)', icon: Italic },
  { kind: 'h2', label: 'Heading', icon: Heading2 },
  { kind: 'h3', label: 'Small heading', icon: Heading3 },
  { kind: 'quote', label: 'Quote', icon: Quote },
  { kind: 'bullets', label: 'Bulleted list', icon: List },
  { kind: 'numbers', label: 'Numbered list', icon: ListOrdered },
  { kind: 'link', label: 'Link (⌘K)', icon: Link2 },
]

/** A Markdown textarea with a formatting bar: select words and press a
 *  button (or ⌘B / ⌘I / ⌘K), and the marks go round them. */
export default function MarkdownField({ value, onChange, rows = 8, placeholder, label }: {
  value: string
  onChange: (value: string) => void
  rows?: number
  placeholder?: string
  label: string
}) {
  const ref = useRef<HTMLTextAreaElement>(null)

  const apply = (kind: MdFormat) => {
    const el = ref.current
    if (!el) return
    const edit = formatMarkdown(value, el.selectionStart, el.selectionEnd, kind)
    onChange(edit.value)
    // After React writes the new text, select what the writer will type over.
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(edit.start, edit.end)
    })
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 focus-within:border-emerald-500">
      <div className="flex flex-wrap gap-0.5 border-b border-zinc-800 px-1.5 py-1" role="toolbar" aria-label={`Format ${label.toLowerCase()}`}>
          {TOOLS.map(({ kind, label: name, icon: Icon }) => (
            <button key={kind} type="button" title={name} aria-label={name}
              // Keep the selection in the textarea while the button is pressed.
              onMouseDown={(e) => e.preventDefault()} onClick={() => apply(kind)}
              className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">
              <Icon className="h-4 w-4" />
            </button>
          ))}
      </div>
      <textarea ref={ref} value={value} rows={rows} placeholder={placeholder} aria-label={label}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          const kind = shortcutFormat(e)
          if (kind) { e.preventDefault(); apply(kind) }
        }}
        className="block w-full resize-y bg-zinc-900 px-3 py-2 font-mono text-[13px] text-zinc-100 outline-none placeholder:text-zinc-500" />
    </div>
  )
}
