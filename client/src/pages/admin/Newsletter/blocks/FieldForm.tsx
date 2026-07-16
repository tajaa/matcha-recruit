import { useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Loader2, ImagePlus, X, Plus, Trash2, ChevronUp, ChevronDown, Bold, List } from 'lucide-react'
import { uploadNewsletterMedia } from '../uploadMedia'
import { LABEL } from '../../../../components/ui/typography'
import type { Field } from './schema'

const inputCls =
  'w-full px-2.5 py-1.5 rounded-lg border border-white/[0.08] bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500'

type Obj = Record<string, unknown>

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Minimal rich-text control: bold + bulleted list only, matching what the
 * server renderer (`email_blocks.py:_render_text`) accepts via a block's
 * `html` key. Remounts fresh each time a block is opened for editing (see
 * NewsletterBuilder's `open && <FieldForm .../>`), so the initial `content`
 * seed below is all that's needed — no external-sync effect. */
function RichTextInput({ html, body, onChange }: { html: string; body: string; onChange: (v: { html: string; body: string }) => void }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        italic: false,
        strike: false,
        code: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
        orderedList: false,
      }),
    ],
    content: html || (body ? `<p>${escapeHtml(body)}</p>` : ''),
    onUpdate: ({ editor: e }) => onChange({ html: e.getHTML(), body: e.getText() }),
    editorProps: {
      attributes: {
        class: 'outline-none min-h-[70px] px-2.5 py-1.5 text-sm text-zinc-200',
      },
    },
  })

  if (!editor) return null

  const tb = (active: boolean) =>
    `p-1 rounded transition-colors ${active ? 'text-emerald-400 bg-zinc-800' : 'text-zinc-500 hover:text-zinc-300'}`

  return (
    <div className="rounded-lg border border-white/[0.08] bg-zinc-900">
      <div className="flex items-center gap-0.5 px-1.5 py-1 border-b border-white/[0.04]">
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleBold().run() }}
          className={tb(editor.isActive('bold'))}
          title="Bold"
        ><Bold size={13} /></button>
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleBulletList().run() }}
          className={tb(editor.isActive('bulletList'))}
          title="Bullet list"
        ><List size={13} /></button>
      </div>
      <EditorContent editor={editor} />
      <style>{`
        .ProseMirror p { margin: 4px 0; }
        .ProseMirror ul { padding-left: 20px; margin: 4px 0; list-style: disc; }
        .ProseMirror li { margin: 2px 0; }
        .ProseMirror strong { color: #e8e8e8; font-weight: 600; }
      `}</style>
    </div>
  )
}

/** Upload-or-paste image control shared by every image field. */
function ImageInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [busy, setBusy] = useState(false)
  async function onFile(file: File) {
    setBusy(true)
    const url = await uploadNewsletterMedia(file)
    setBusy(false)
    if (url) onChange(url)
    else alert('Upload failed — try another file.')
  }
  return (
    <div className="space-y-1.5">
      {value ? (
        <div className="relative inline-block">
          <img src={value} alt="" className="max-h-28 rounded-lg border border-white/[0.08] object-cover" />
          <button
            type="button"
            onClick={() => onChange('')}
            className="absolute top-1 right-1 p-1 rounded-md bg-black/60 text-zinc-200 hover:text-white"
          >
            <X size={12} />
          </button>
        </div>
      ) : (
        <label className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-dashed border-white/[0.08] text-xs text-zinc-400 hover:border-emerald-600/60 hover:text-zinc-300 cursor-pointer">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}
          {busy ? 'Uploading…' : 'Upload image'}
          <input
            type="file" accept="image/*,video/*" className="hidden" disabled={busy}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }}
          />
        </label>
      )}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="…or paste an image URL"
        className={inputCls}
      />
    </div>
  )
}

/** A single field bound to obj[field.key]. */
function FieldRow({ field, obj, onChange }: { field: Field; obj: Obj; onChange: (next: Obj) => void }) {
  const value = obj[field.key]
  const set = (v: unknown) => onChange({ ...obj, [field.key]: v })

  if (field.kind === 'bool') {
    return (
      <label className="flex items-center gap-2 cursor-pointer py-1">
        <input type="checkbox" checked={!!value} onChange={(e) => set(e.target.checked)} className="accent-emerald-500" />
        <span className="text-xs text-zinc-300">{field.label}</span>
      </label>
    )
  }

  return (
    <div className="space-y-1">
      <label className={LABEL}>{field.label}</label>
      {field.kind === 'text' && (
        <input value={(value as string) ?? ''} onChange={(e) => set(e.target.value)} placeholder={field.placeholder} className={inputCls} />
      )}
      {field.kind === 'textarea' && (
        <textarea value={(value as string) ?? ''} onChange={(e) => set(e.target.value)} placeholder={field.placeholder} rows={3} className={`${inputCls} resize-y`} />
      )}
      {field.kind === 'select' && (
        <select value={(value as string) ?? ''} onChange={(e) => set(e.target.value)} className={inputCls}>
          {field.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
      {field.kind === 'image' && <ImageInput value={(value as string) ?? ''} onChange={set} />}
      {field.kind === 'list' && <ListField field={field} value={(value as Obj[]) ?? []} onChange={set} />}
      {field.kind === 'rich' && (
        <RichTextInput
          html={(obj.html as string) ?? ''}
          body={(value as string) ?? ''}
          onChange={({ html, body }) => onChange({ ...obj, [field.key]: body, html })}
        />
      )}
      {field.help && <p className="text-[10px] text-zinc-600 leading-snug">{field.help}</p>}
    </div>
  )
}

/** Repeatable list of sub-objects (features, columns, articles, socials, stats). */
function ListField({ field, value, onChange }: { field: Field; value: Obj[]; onChange: (v: Obj[]) => void }) {
  const items = value ?? []
  const update = (i: number, next: Obj) => onChange(items.map((it, idx) => (idx === i ? next : it)))
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i))
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= items.length) return
    const copy = items.slice()
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
    onChange(copy)
  }
  const add = () => onChange([...items, (field.newItem?.() ?? {}) as Obj])

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="rounded-lg border border-white/[0.06] bg-zinc-900/40 p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className={LABEL}>Item {i + 1}</span>
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="text-zinc-500 hover:text-zinc-300 disabled:opacity-30"><ChevronUp size={13} /></button>
              <button type="button" onClick={() => move(i, 1)} disabled={i === items.length - 1} className="text-zinc-500 hover:text-zinc-300 disabled:opacity-30"><ChevronDown size={13} /></button>
              <button type="button" onClick={() => remove(i)} className="text-zinc-500 hover:text-red-400"><Trash2 size={12} /></button>
            </div>
          </div>
          {(field.item ?? []).map((sub) => (
            <FieldRow key={sub.key} field={sub} obj={item} onChange={(next) => update(i, next)} />
          ))}
        </div>
      ))}
      <button
        type="button" onClick={add}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-dashed border-white/[0.08] text-xs text-zinc-400 hover:text-zinc-200 hover:border-emerald-600/60 w-full justify-center"
      >
        <Plus size={13} /> {field.addLabel ?? 'Add item'}
      </button>
    </div>
  )
}

/** Render a set of fields against a value object. */
export function FieldForm({ fields, value, onChange }: { fields: Field[]; value: Obj; onChange: (next: Obj) => void }) {
  if (!fields.length) return <p className="text-xs text-zinc-500 italic">This block has no settings.</p>
  return (
    <div className="space-y-3">
      {fields.map((f) => <FieldRow key={f.key} field={f} obj={value} onChange={onChange} />)}
    </div>
  )
}
