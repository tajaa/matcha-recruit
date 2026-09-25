import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../api/client'
import {
  createTicketDraft, generateTicketDraft, getGithubConnection, listProjectElements,
  listTicketDraftMessages, listTicketDrafts, patchTicketDraft, promoteTicketDraft,
  sendTicketDraftMessage,
} from '../../api/matchaWork'
import type { ProjectElement, TicketDraft, TicketDraftMessage } from '../../api/matchaWork'
import { autoSyncFromGithubIfStale } from '../../utils/githubAutoSync'

interface Props { projectId: string; canEdit: boolean; onPromoted: (taskId: string) => void }

export default function ProjectPropsTab({ projectId, canEdit, onPromoted }: Props) {
  const [drafts, setDrafts] = useState<TicketDraft[]>([])
  const [elements, setElements] = useState<ProjectElement[]>([])
  const [selected, setSelected] = useState<TicketDraft | null>(null)
  const [messages, setMessages] = useState<TicketDraftMessage[]>([])
  const [message, setMessage] = useState('')
  const [title, setTitle] = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewPriority, setReviewPriority] = useState<TicketDraft['priority']>('medium')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const promoting = useRef(false)

  useEffect(() => {
    let active = true
    Promise.all([listTicketDrafts(projectId), listProjectElements(projectId), getGithubConnection(projectId)])
      .then(async ([rows, elems, connection]) => {
        if (!active) return
        setDrafts(rows)
        setElements(elems.filter((element) => element.kind !== '_repository_snapshot'))
        const synced = await autoSyncFromGithubIfStale(projectId, connection.connected)
        if (synced && active) setElements((await listProjectElements(projectId)).filter((element) => element.kind !== '_repository_snapshot'))
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load Props.') })
    return () => { active = false }
  }, [projectId])

  async function openDraft(draft: TicketDraft) {
    setSelected(draft)
    setTitle(draft.title ?? '')
    setReviewPriority(draft.priority ?? 'medium')
    setError(null)
    try { setMessages(await listTicketDraftMessages(projectId, draft.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load messages.') }
  }

  async function create(kind: 'feat' | 'fix') {
    setBusy(true)
    try {
      const draft = await createTicketDraft(projectId, kind)
      setDrafts((rows) => [draft, ...rows])
      await openDraft(draft)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create Prop.') }
    finally { setBusy(false) }
  }

  async function save(patch: Partial<TicketDraft>) {
    if (!selected) return
    try {
      const updated = await patchTicketDraft(projectId, selected.id, patch)
      setSelected(updated)
      setDrafts((rows) => rows.map((row) => row.id === updated.id ? updated : row))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save Prop.') }
  }

  async function send() {
    const content = message.trim()
    if (!selected || !content || busy) return
    setBusy(true); setError(null)
    try {
      const result = await sendTicketDraftMessage(projectId, selected.id, content)
      // The server returns the committed pair; no optimistic echo.
      setMessages((rows) => [...rows, result.user_message, result.assistant_message])
      setMessage('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not send message.') }
    finally { setBusy(false) }
  }

  async function generate() {
    if (!selected || busy) return
    setBusy(true); setError(null)
    try {
      const updated = await generateTicketDraft(projectId, selected.id)
      setSelected(updated)
      setTitle(updated.title ?? '')
      setReviewPriority(updated.priority ?? 'medium')
      setDrafts((rows) => rows.map((row) => row.id === updated.id ? updated : row))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not generate draft.') }
    finally { setBusy(false) }
  }

  async function promote() {
    if (!selected || !canEdit || selected.status === 'promoted' || !title.trim() || busy || promoting.current) return
    promoting.current = true
    setBusy(true); setError(null)
    try {
      const task = await promoteTicketDraft(projectId, selected.id, {
        title: title.trim(), category: selected.kind, board_column: 'todo', priority: reviewPriority,
      })
      setReviewOpen(false)
      setSelected(null)
      setDrafts(await listTicketDrafts(projectId))
      onPromoted(task.id)
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 404
        ? 'This Prop was already promoted or removed by someone else.'
        : cause instanceof Error ? cause.message : 'Could not promote Prop.')
      // Another collaborator may have promoted it; refresh before allowing retry.
      const rows = await listTicketDrafts(projectId).catch(() => [])
      setDrafts(rows)
      setSelected(rows.find((row) => row.id === selected.id) ?? null)
      if (cause instanceof ApiError && cause.status === 404) setReviewOpen(false)
    } finally { promoting.current = false; setBusy(false) }
  }

  if (!selected) return <div className="h-full space-y-4 overflow-y-auto p-4 text-sm text-w-text">
    <header><h2 className="text-lg font-semibold">Props</h2><p className="text-xs text-w-dim">Shape a feature or fix before turning it into a task.</p></header>
    {error && <p role="alert" className="text-orange-400">{error}</p>}
    {canEdit && <div className="flex gap-2"><button disabled={busy} onClick={() => void create('feat')} className="rounded bg-w-accent px-3 py-1.5 text-white">New Feat</button><button disabled={busy} onClick={() => void create('fix')} className="rounded border border-w-line px-3 py-1.5">New Fix</button></div>}
    {drafts.map((draft) => <button key={draft.id} onClick={() => void openDraft(draft)} className="block w-full rounded border border-w-line p-3 text-left hover:bg-w-surface">
      <span className="font-semibold">{draft.kind === 'feat' ? '✦' : '◆'} {draft.title || 'Untitled Prop'}</span>
      {draft.status === 'promoted' && <span className="ml-2 text-xs text-w-accent">Promoted</span>}
      {draft.element_id && <p className="text-xs text-w-dim">{elements.find((element) => element.id === draft.element_id)?.name ?? draft.element_id}</p>}
    </button>)}
    {!drafts.length && <p className="text-w-dim">No Props yet.</p>}
  </div>

  return <div className="flex h-full min-h-0 flex-col text-sm text-w-text">
    <header className="flex items-center gap-2 border-b border-w-line p-3">
      <button onClick={() => { setSelected(null); setReviewOpen(false) }} className="text-w-accent">← Props</button>
      <span className="font-semibold">{selected.kind === 'feat' ? 'Feat' : 'Fix'}</span>
      {selected.status === 'promoted' && <span className="text-xs text-w-accent">Promoted</span>}
    </header>
    {error && <p role="alert" className="px-3 pt-2 text-orange-400">{error}</p>}
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
      <label className="block text-xs text-w-dim">Code element
        <select value={selected.element_id ?? ''} onChange={(event) => void save({ element_id: event.target.value })} className="mt-1 w-full rounded border border-w-line bg-w-surface p-2 text-w-text">
          <option value="">No grounding</option>
          {elements.map((element) => <option key={element.id} value={element.id}>{element.name}</option>)}
        </select>
      </label>
      <div className="space-y-2 rounded border border-w-line p-3">
        <label className="block text-xs text-w-dim">Title
          <input value={title} onChange={(event) => setTitle(event.target.value)} onBlur={() => { if (title.trim() !== (selected.title ?? '')) void save({ title: title.trim() }) }} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void save({ title: title.trim() }) } }} className="mt-1 w-full rounded border border-w-line bg-w-surface p-2 text-w-text" />
        </label>
        {selected.description && <p className="whitespace-pre-wrap">{selected.description}</p>}
        {selected.draft_subtasks?.length > 0 && <ul className="list-inside list-disc text-w-dim">{selected.draft_subtasks.map((step, index) => <li key={`${index}:${step}`}>{step}</li>)}</ul>}
        <div className="flex gap-2"><button disabled={busy || selected.status === 'promoted'} onClick={() => void generate()} className="rounded border border-w-line px-2 py-1 disabled:opacity-50">Generate draft</button><button disabled={!canEdit || busy || selected.status === 'promoted' || !title.trim()} onClick={() => setReviewOpen(true)} className="rounded bg-w-accent px-2 py-1 text-white disabled:opacity-50">Promote to task</button></div>
      </div>
      <section className="space-y-2" aria-label="Prop conversation">
        {messages.map((item) => <p key={item.id} className={`whitespace-pre-wrap rounded p-2 ${item.role === 'user' ? 'bg-w-accent/10' : 'bg-w-surface'}`}><span className="mb-1 block text-xs font-medium text-w-dim">{item.role === 'user' ? 'You' : 'Espresso'}</span>{item.content}</p>)}
      </section>
    </div>
    <div className="flex gap-2 border-t border-w-line p-3"><textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={2} placeholder="Ask about the code or shape this ticket…" className="min-w-0 flex-1 rounded border border-w-line bg-w-surface p-2" /><button disabled={busy || !message.trim()} onClick={() => void send()} className="rounded bg-w-accent px-3 text-white disabled:opacity-50">Send</button></div>
    {reviewOpen && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"><div className="w-full max-w-md space-y-3 rounded bg-w-bg p-4"><h3 className="font-semibold">Review task</h3><input value={title} onChange={(event) => setTitle(event.target.value)} className="w-full rounded border border-w-line bg-w-surface p-2" /><select value={reviewPriority} onChange={(event) => setReviewPriority(event.target.value as TicketDraft['priority'])} className="w-full rounded border border-w-line bg-w-surface p-2">{['critical', 'high', 'medium', 'low'].map((priority) => <option key={priority} value={priority}>{priority}</option>)}</select><p className="text-xs text-w-dim">{selected.kind} · To Do · {selected.draft_subtasks?.length ?? 0} checklist steps</p><div className="flex gap-2"><button disabled={busy || !title.trim()} onClick={() => void promote()} className="rounded bg-w-accent px-3 py-1.5 text-white disabled:opacity-50">Confirm promotion</button><button onClick={() => setReviewOpen(false)}>Cancel</button></div></div></div>}
  </div>
}
