import { useEffect, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cappeApi } from '../../api'
import LibraryPanel from '../../magazine/library/LibraryPanel'
import type { CappeAsset, CappeStoryOptions } from '../../types'
import { studioApi, toAsset, type Revision, type StudioPost } from '../api'
import { addItem, patchItems } from '../model/ops'
import { useStudio } from '../store/store'
import { useCtx } from './context'

function Dialog({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={`flex max-h-full w-full flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 text-zinc-100 shadow-2xl ${wide ? 'max-w-5xl' : 'max-w-lg'}`}>
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><X className="h-4 w-4" /></button>
        </div>
        <div className="min-h-0 overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}

/** The picture library, to fill the picture frame selected (or a new frame
 *  on the page in view, at the picture's shape). */
export function LibraryDialog() {
  const c = useCtx()
  const { store } = c
  const close = () => store.set({ dialog: null })
  const pick = (a: CappeAsset) => {
    const s = store.get()
    store.set((x) => ({ assets: { ...x.assets, [a.id]: toAsset(a) } }))
    const frame = s.doc.items.find((i) => s.selection.includes(i.id) && i.kind === 'image')
    if (frame) store.edit((d) => patchItems(d, [frame.id], { asset_id: a.id }))
    else {
      const { w: pw, h: ph } = s.doc.size
      const ratio = a.width && a.height ? a.width / a.height : 1.5
      const w = Math.min(pw - s.doc.margins.i - s.doc.margins.o, (ph / 2) * ratio)
      const h = w / ratio
      let id = ''
      store.edit((d) => {
        const r = addItem(d, 'image', d.pages[s.page].id, { x: (pw - w) / 2, y: (ph - h) / 2, w, h })
        id = r.id
        return patchItems(r.doc, [r.id], { asset_id: a.id })
      })
      store.set({ selection: [id], tool: 'select' })
    }
    close()
  }
  return (
    <Dialog title="Place a picture" onClose={close} wide>
      <div className="p-2"><LibraryPanel siteId={c.siteId} postId={c.postId} onPick={pick} /></div>
    </Dialog>
  )
}

/** What isn't on the pages: the headline readers see in lists, the dek, the
 *  byline, the topic, who can read it. */
export function StoryDialog() {
  const c = useCtx()
  const close = () => c.store.set({ dialog: null })
  const [form, setForm] = useState<StudioPost>(c.post)
  const [topics, setTopics] = useState<{ key: string; label: string }[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    cappeApi.get<CappeStoryOptions>(`/sites/${c.siteId}/stories/options`).then((o) => setTopics(o.topics), () => {})
  }, [c.siteId])
  const field = (key: keyof StudioPost, label: string, max: number, area = false) => (
    <label className="block">
      <span className="mb-1 block text-[11px] text-zinc-400">{label}</span>
      {area
        ? <textarea rows={2} maxLength={max} value={(form[key] as string) ?? ''} onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm outline-none focus:border-emerald-500" />
        : <input maxLength={max} value={(form[key] as string) ?? ''} onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm outline-none focus:border-emerald-500" />}
    </label>
  )
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const saved = await studioApi.updatePost(c.siteId, c.postId, {
        title: form.title.trim() || 'Untitled story', kicker: form.kicker || null, excerpt: form.excerpt || null,
        byline: form.byline || null, topic: form.topic || null, access: form.access,
      })
      c.setPost({ ...c.post, ...saved })
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Couldn’t save the story’s settings.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog title="Story settings" onClose={close}>
      <div className="space-y-3 p-4">
        {field('title', 'Headline (in lists, emails and search)', 255)}
        {field('kicker', 'Kicker', 60)}
        {field('excerpt', 'Dek', 600, true)}
        {field('byline', 'Byline', 160)}
        <label className="block">
          <span className="mb-1 block text-[11px] text-zinc-400">Topic</span>
          <select value={form.topic ?? ''} onChange={(e) => setForm({ ...form, topic: e.target.value || null })}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm outline-none">
            <option value="">None</option>
            {topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </label>
        <fieldset className="space-y-1">
          <legend className="mb-1 text-[11px] text-zinc-400">Who can read it</legend>
          {(['free', 'paid'] as const).map((a) => (
            <label key={a} className="flex items-center gap-2 text-sm">
              <input type="radio" name="access" checked={form.access === a} onChange={() => setForm({ ...form, access: a })} className="accent-emerald-500" />
              {a === 'free' ? 'Everyone' : 'Subscribers, from the page set in Pages → Document'}
            </label>
          ))}
        </fieldset>
        {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={close} className="rounded-md px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">Cancel</button>
          <button type="button" disabled={busy} onClick={submit}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">Save</button>
        </div>
      </div>
    </Dialog>
  )
}

const KIND: Record<Revision['kind'], string> = { save: 'Saved', publish: 'Went live', restore: 'Restored', convert: 'Converted' }

/** Earlier versions: each kept save, each update of the live story. */
export function RevisionsDialog() {
  const c = useCtx()
  const rev = useStudio(c.store, (s) => s.save.rev)
  const close = () => c.store.set({ dialog: null })
  const [list, setList] = useState<Revision[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    studioApi.revisions(c.siteId, c.postId).then(setList, (err) => setError(err instanceof Error ? err.message : 'Couldn’t load versions.'))
  }, [c.siteId, c.postId])
  const restore = async (r: Revision) => {
    try {
      await c.save()
      const saved = await studioApi.restore(c.siteId, c.postId, r.id, c.store.get().save.rev)
      c.store.replace(saved.doc, { save: { ...c.store.get().save, rev: saved.rev, draft: saved.draft, state: 'saved', message: null } })
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Couldn’t restore it.')
    }
  }
  return (
    <Dialog title="Versions" onClose={close}>
      <div className="p-2">
        {error && <p role="alert" className="p-2 text-xs text-red-300">{error}</p>}
        {!list && !error && <p className="p-3 text-xs text-zinc-500">Loading…</p>}
        {list && !list.length && <p className="p-3 text-xs text-zinc-500">No versions kept yet. ⌘S keeps one; each update of the live story does too.</p>}
        {list?.map((r) => (
          <div key={r.id} className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-zinc-800">
            <div>
              <p className="text-sm text-zinc-100">{KIND[r.kind]}</p>
              <p className="text-[11px] text-zinc-500">{new Date(r.created_at).toLocaleString()} · revision {r.rev}{r.rev === rev ? ' (now)' : ''}</p>
            </div>
            <button type="button" onClick={() => void restore(r)} className="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:border-emerald-500">Restore</button>
          </div>
        ))}
      </div>
    </Dialog>
  )
}
