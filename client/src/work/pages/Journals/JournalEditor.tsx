import { useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Eye, ImagePlus, Pencil, Users } from 'lucide-react'
import {
  createJournalEntry, listJournalEntries, updateJournalEntry, uploadJournalImage,
  type Journal, type JournalEntry, type JournalFolder,
} from '../../api/matchaWork/journals'
import CollaboratorsModal from './CollaboratorsModal'
import { createQuickTodo } from '../../api/matchaWork/productivity'

const slashActions = [
  { label: 'Heading 1', marker: '# ' }, { label: 'Heading 2', marker: '## ' },
  { label: 'Heading 3', marker: '### ' }, { label: 'Bullet list', marker: '- ' },
  { label: 'To-do', marker: '- [ ] ' }, { label: 'Quote', marker: '> ' },
  { label: 'Code block', marker: '```\n\n```' },
]

type Draft = { entryId: string | null; content: string; saved: string }

const SHORTCUT_MARKERS: Record<string, string> = {
  Digit1: '# ',
  Digit2: '## ',
  Digit3: '### ',
  KeyT: '- [ ] ',
}

export default function JournalEditor({ journal, folders, userId, onRename, onMove, onChanged }: {
  journal: Journal
  folders: JournalFolder[]
  userId: string | undefined
  onRename: (title: string) => Promise<unknown>
  onMove: (folderId: string | null) => Promise<unknown>
  onChanged: () => void
}) {
  const [title, setTitle] = useState(journal.title)
  const [content, setContent] = useState('')
  const [entryAuthorId, setEntryAuthorId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(false)
  const [showCollaborators, setShowCollaborators] = useState(false)
  const [slashMenu, setSlashMenu] = useState(false)
  const [selectionMenu, setSelectionMenu] = useState<{ excerpt: string; x: number; y: number } | null>(null)
  const textArea = useRef<HTMLTextAreaElement>(null)
  const imageInput = useRef<HTMLInputElement>(null)
  const draft = useRef<Draft>({ entryId: null, content: '', saved: '' })
  const draining = useRef<Promise<void> | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const flush = useCallback((): Promise<void> => {
    if (draining.current) return draining.current
    if (!draft.current.entryId || draft.current.content === draft.current.saved) return Promise.resolve()
    const task = (async () => {
      while (draft.current.entryId && draft.current.content !== draft.current.saved) {
        const entryId = draft.current.entryId
        const body = draft.current.content
        try {
          setStatus('Saving…')
          await updateJournalEntry(journal.id, entryId, { content: body })
          draft.current.saved = body
          setStatus('Saved')
          setError('')
        } catch (cause) {
          setStatus('Save failed')
          setError(cause instanceof Error ? cause.message : 'Could not save note')
          return
        }
      }
      onChanged()
    })()
    draining.current = task
    void task.finally(() => { draining.current = null })
    return task
  }, [journal.id, onChanged])

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const entries = await listJournalEntries(journal.id)
        const entry: JournalEntry = (journal.created_by === userId ? entries[0] : entries.find((item) => item.author_id === userId) ?? entries[0])
          ?? await createJournalEntry(journal.id, { content: '' })
        if (!active) return
        draft.current = { entryId: entry.id, content: entry.content, saved: entry.content }
        setContent(entry.content)
        setEntryAuthorId(entry.author_id)
        setError('')
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not open note')
      } finally { if (active) setLoading(false) }
    })()
    return () => { active = false; if (timer.current) clearTimeout(timer.current); void flush() }
  }, [journal.id, journal.created_by, userId, flush])

  function change(next: string) {
    setSelectionMenu(null)
    draft.current.content = next
    setContent(next)
    setStatus('Unsaved')
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => { void flush() }, 800)
    const cursor = textArea.current?.selectionStart ?? next.length
    const line = next.slice(next.lastIndexOf('\n', cursor - 1) + 1, cursor)
    setSlashMenu(/^\/[a-z]*$/i.test(line))
  }

  function replaceLine(marker: string) {
    const input = textArea.current
    if (!input) return
    const cursor = input.selectionStart
    const start = content.lastIndexOf('\n', cursor - 1) + 1
    change(content.slice(0, start) + marker + content.slice(cursor))
    setSlashMenu(false)
    requestAnimationFrame(() => { input.focus(); input.setSelectionRange(start + marker.length, start + marker.length) })
  }

  // Keyboard shortcuts restyle the current line in place: swap any existing
  // heading/to-do marker for the new one and keep the line's text. (The
  // slash menu uses replaceLine instead, which also drops the typed "/cmd".)
  function prefixLine(marker: string) {
    const input = textArea.current
    if (!input) return
    const cursor = input.selectionStart
    const start = content.lastIndexOf('\n', cursor - 1) + 1
    const rest = content.slice(start)
    const existing = /^(?:#{1,6} |- \[[ xX]\] )/.exec(rest)?.[0] ?? ''
    change(content.slice(0, start) + marker + rest.slice(existing.length))
    const next = Math.max(start + marker.length, cursor + marker.length - existing.length)
    requestAnimationFrame(() => { input.focus(); input.setSelectionRange(next, next) })
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!editable) return
    // Match on `code`, not `key`: on macOS Option+Shift rewrites `key`
    // (Option+Shift+1 is "⁄"), so a key-based check never fires there.
    const marker = event.altKey && event.shiftKey ? SHORTCUT_MARKERS[event.code] : undefined
    if (marker) {
      event.preventDefault()
      prefixLine(marker)
      return
    }
    if (event.key !== 'Tab') return
    const input = event.currentTarget
    const start = content.lastIndexOf('\n', input.selectionStart - 1) + 1
    const line = content.slice(start, content.indexOf('\n', start) < 0 ? undefined : content.indexOf('\n', start))
    if (!/^\s*(?:[-*+] |\d+\. )/.test(line)) return
    event.preventDefault()
    const next = event.shiftKey ? line.replace(/^ {1,2}/, '') : `  ${line}`
    change(content.slice(0, start) + next + content.slice(start + line.length))
  }

  async function upload(file: File) {
    if (!file.type.startsWith('image/') || file.size > 10 * 1024 * 1024) { setError('Choose an image smaller than 10 MB'); return }
    try {
      const { url } = await uploadJournalImage(journal.id, file)
      const cursor = textArea.current?.selectionStart ?? draft.current.content.length
      const markdown = `![](${url})`
      change(draft.current.content.slice(0, cursor) + markdown + draft.current.content.slice(cursor))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Image upload failed') }
  }

  const editable = journal.created_by === userId || entryAuthorId === userId

  async function startMyEntry() {
    try {
      const entry = await createJournalEntry(journal.id, { content: '' })
      draft.current = { entryId: entry.id, content: '', saved: '' }
      setEntryAuthorId(entry.author_id)
      setContent('')
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create entry') }
  }

  async function captureTodo() {
    if (!selectionMenu) return
    const excerpt = selectionMenu.excerpt
    setSelectionMenu(null)
    try {
      await createQuickTodo({ title: excerpt.split('\n')[0].slice(0, 120), source_journal_id: journal.id, source_excerpt: excerpt })
      setStatus('To-do added')
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create to-do') }
  }

  return (
    <div className="flex min-h-80 min-w-0 flex-1 flex-col overflow-hidden bg-w-bg md:min-h-0">
      <header className="flex flex-wrap items-center gap-2 border-b border-w-line px-4 py-3">
        <input aria-label="Journal title" value={title} disabled={journal.created_by !== userId} onChange={(event) => setTitle(event.target.value)} onBlur={() => {
          const next = title.trim()
          if (next && next !== journal.title) void onRename(next).catch((cause: unknown) => setError(String(cause)))
        }} className="min-w-0 flex-1 bg-transparent text-lg font-semibold text-w-text outline-none disabled:opacity-70" />
        <span aria-live="polite" className="text-[11px] text-w-faint">{status}</span>
        {journal.created_by === userId && <select aria-label="Move note to notebook" value={journal.folder_id ?? ''} onChange={(event) => void onMove(event.target.value || null).catch((cause: unknown) => setError(String(cause)))} className="max-w-32 rounded border border-w-line bg-w-surface2 px-2 py-1 text-xs text-w-text">
          <option value="">Hub root</option>
          {folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
        </select>}
        <button onClick={() => setShowCollaborators(true)} title="Collaborators" aria-label="Collaborators" className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2"><Users size={16} /></button>
        <button onClick={() => setPreview((value) => !value)} title={preview ? 'Edit' : 'Preview'} aria-label={preview ? 'Edit' : 'Preview'} className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2">{preview ? <Pencil size={16} /> : <Eye size={16} />}</button>
      </header>
      {error && <p role="alert" className="px-4 pt-2 text-xs text-red-400">{error}</p>}
      {loading ? <p className="p-5 text-sm text-w-faint">Opening note…</p> : preview ? (
        <article className="prose prose-invert max-w-none flex-1 overflow-y-auto p-6 text-w-text"><Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown></article>
      ) : <>
        <div className="flex items-center gap-2 border-b border-w-line px-4 py-2 text-xs text-w-dim">
          {editable ? <button onClick={() => imageInput.current?.click()} className="flex items-center gap-1 rounded px-2 py-1 hover:bg-w-surface2"><ImagePlus size={14} /> Image</button> : <button onClick={() => void startMyEntry()} className="rounded bg-w-surface2 px-2 py-1 text-w-text">Write my own entry</button>}
          <input ref={imageInput} type="file" accept="image/*" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '' }} />
          <details className="relative"><summary className="cursor-pointer">Editor help</summary><div className="absolute left-0 top-full z-10 w-64 rounded border border-w-line bg-w-surface p-3 shadow-xl">Type / at the start of a line for blocks. Alt+Shift+1–3 adds headings; Alt+Shift+T adds a to-do. Tab and Shift+Tab indent list items. Paste or drop images to upload.</div></details>
        </div>
        {slashMenu && <div className="flex flex-wrap gap-1 border-b border-w-line px-4 py-2">{slashActions.map((action) => <button key={action.label} onMouseDown={(event) => event.preventDefault()} onClick={() => replaceLine(action.marker)} className="rounded bg-w-surface2 px-2 py-1 text-xs text-w-text hover:bg-w-line">{action.label}</button>)}</div>}
        <textarea ref={textArea} aria-label="Journal content" value={content} readOnly={!editable} onChange={(event) => change(event.target.value)} onBlur={() => void flush()} onKeyDown={onKeyDown} onContextMenu={(event) => {
          const input = event.currentTarget
          const excerpt = input.value.slice(input.selectionStart, input.selectionEnd).trim().slice(0, 1_000)
          if (!excerpt) return
          event.preventDefault()
          setSelectionMenu({ excerpt, x: event.clientX, y: event.clientY })
        }} onPaste={(event) => {
          if (!editable) return
          const file = [...event.clipboardData.files].find((candidate) => candidate.type.startsWith('image/'))
          if (file) { event.preventDefault(); void upload(file) }
        }} onDragOver={(event) => { if (editable) event.preventDefault() }} onDrop={(event) => { if (!editable) return; event.preventDefault(); const file = [...event.dataTransfer.files].find((candidate) => candidate.type.startsWith('image/')); if (file) void upload(file) }} spellCheck className="min-h-0 flex-1 resize-none bg-transparent p-6 font-mono text-sm leading-7 text-w-text outline-none placeholder:text-w-faint" placeholder="Start writing…" />
        {selectionMenu && <button onMouseDown={(event) => event.preventDefault()} onClick={() => void captureTodo()} style={{ position: 'fixed', left: selectionMenu.x, top: selectionMenu.y }} className="z-50 rounded-md border border-w-line bg-w-surface px-3 py-2 text-xs text-w-text shadow-xl">Add selection to to-dos</button>}
      </>}
      {showCollaborators && <CollaboratorsModal journal={journal} userId={userId} onClose={() => setShowCollaborators(false)} onChanged={onChanged} />}
    </div>
  )
}
