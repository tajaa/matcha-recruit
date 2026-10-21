import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Eye, Loader2, Redo2, Trash2, Undo2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import { useUnsavedGuard } from '../../pages/site/PageEditor/useUnsavedGuard'
import type {
  CappeAsset, CappeMagazine, CappeMagazineIssue, CappeMagazineIssueOptions, CappePost, ContentsDesign, CoverDesign,
  IssueStoryRef,
} from '../../types'
import { confirmLeave } from '../../utils/unsavedGuard'
import { useHistory } from '../editor/history'
import LibraryPanel from '../library/LibraryPanel'
import BookFrame from '../reader/BookFrame'
import ContentsPanel from './ContentsPanel'
import CoverPanel from './CoverPanel'
import IssueStories, { type StoryInfo } from './IssueStories'
import { addStories, docOf, removeStory, saveBody, type IssueDoc } from './issueDoc'
import StoryPicker from './StoryPicker'

type Tab = 'stories' | 'cover' | 'contents'
const TABS: { key: Tab; label: string }[] = [
  { key: 'stories', label: 'Stories' }, { key: 'cover', label: 'Cover' }, { key: 'contents', label: 'Contents' },
]

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const MOD = isMac ? '⌘' : 'Ctrl+'
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** `sites/:siteId/issues/:issueId` — one issue: the stories it holds and in
 *  what order, its cover and its contents, with the whole issue previewed
 *  as the book readers will turn. Releasing it publishes its draft stories;
 *  a released issue stays editable and each save goes live. */
export default function IssueEditor() {
  const { siteId, issueId } = useParams<{ siteId: string; issueId: string }>()
  const navigate = useNavigate()
  const [issue, setIssue] = useState<CappeMagazineIssue | null>(null)
  const doc = useHistory<IssueDoc | null>(null)
  const { set: setDoc, reset: resetDoc, replace: replaceDoc } = doc
  const current = doc.value
  const [options, setOptions] = useState<CappeMagazineIssueOptions | null>(null)
  const [posts, setPosts] = useState<StoryInfo[]>([])
  const [assets, setAssets] = useState<Map<string, CappeAsset>>(new Map())
  const [name, setName] = useState('')
  const [tab, setTab] = useState<Tab>('stories')
  const [preview, setPreview] = useState('')
  const [previewOpen, setPreviewOpen] = useState(true)
  const [picking, setPicking] = useState<'photo' | 'stories' | null>(null)
  const [busy, setBusy] = useState<'' | 'save' | 'release' | 'withdraw'>('')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const previewGen = useRef(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      cappeApi.get<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues/${issueId}`),
      cappeApi.get<CappeMagazineIssueOptions>(`/sites/${siteId}/magazine/issues/options`),
      cappeApi.get<CappePost[]>(`/sites/${siteId}/posts`),
      cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${siteId}/assets`),
      cappeApi.get<CappeMagazine>(`/sites/${siteId}/magazine`).catch(() => null),
    ]).then(([i, o, p, a, m]) => {
      if (cancelled) return
      setIssue(i)
      resetDoc(docOf(i))
      setOptions(o)
      setPosts(p)
      setAssets(new Map(a.assets.map((x) => [x.id, x])))
      setName(m?.name || '')
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the issue') })
    return () => { cancelled = true }
  }, [siteId, issueId, resetDoc])

  const info = useMemo(() => new Map(posts.map((p) => [p.id, p])), [posts])
  const taken = useMemo(() => new Map((options?.taken || []).filter((t) => t.issue_id !== issueId)
    .map((t) => [t.post_id, t.number])), [options, issueId])
  const dirty = useMemo(() => !!issue && !!current
    && JSON.stringify(saveBody(current)) !== JSON.stringify(saveBody(docOf(issue))), [issue, current])
  const drafts = (current?.stories || []).filter((s) => info.get(s.post_id)?.status === 'draft').length
  const released = issue?.status === 'released'

  // The preview follows the editor, a moment after a change settles.
  useEffect(() => {
    if (!current || !previewOpen) return
    const gen = ++previewGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/magazine/issues/preview`, { issue_id: issueId, ...saveBody(current) })
        .then((html) => { if (gen === previewGen.current) setPreview(html) })
        .catch(() => { /* the last good preview stays up */ })
    }, 600)
    return () => clearTimeout(t)
  }, [siteId, issueId, current, previewOpen])

  const setStories = useCallback((stories: IssueStoryRef[], step = false) =>
    setDoc((d) => (d ? { ...d, stories } : d), { step }), [setDoc])
  const setCover = useCallback((cover: CoverDesign, step = false) => setDoc((d) => (d ? { ...d, cover } : d), { step }), [setDoc])
  const setContents = useCallback((contents: ContentsDesign, step = false) =>
    setDoc((d) => (d ? { ...d, contents } : d), { step }), [setDoc])

  /** What the server sent back after a save or release; drafts it published
   *  are published here too. */
  const took = (updated: CappeMagazineIssue) => {
    setIssue(updated)
    replaceDoc(docOf(updated))
    if (updated.published.length) {
      const ids = new Set(updated.stories.map((s) => s.post_id))
      setPosts((ps) => ps.map((p) => (ids.has(p.id) && p.status === 'draft' ? { ...p, status: 'published' } : p)))
      setNote(`Published with the issue: ${updated.published.join(', ')}.`)
    }
  }

  const save = async (): Promise<boolean> => {
    if (!current) return false
    setBusy('save')
    setError(null)
    setNote(null)
    try {
      took(await cappeApi.put<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues/${issueId}`, saveBody(current)))
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
      return false
    } finally {
      setBusy('')
    }
  }

  const release = async () => {
    if (!current || !issue) return
    const extra = drafts ? ` ${drafts === 1 ? 'Its draft story' : `Its ${drafts} draft stories`} will be published with it.` : ''
    if (!window.confirm(`Release No. ${current.number}? It goes on your magazine at once.${extra}`)) return
    if (dirty && !(await save())) return
    setBusy('release')
    setError(null)
    try {
      took(await cappeApi.post<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues/${issueId}/release`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not release the issue')
    } finally {
      setBusy('')
    }
  }

  const withdraw = async () => {
    if (!issue || !window.confirm(`Take No. ${issue.number} off your magazine? Its stories stay published.`)) return
    setBusy('withdraw')
    setError(null)
    try {
      took(await cappeApi.post<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues/${issueId}/withdraw`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not withdraw the issue')
    } finally {
      setBusy('')
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this issue? Its stories stay as they are.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}/magazine/issues/${issueId}`)
      navigate(`/cappe/sites/${siteId}/issues`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete the issue')
    }
  }

  useUnsavedGuard(() => dirty)

  // ⌘S saves, ⌘Z undoes, ⇧⌘Z (or ⌘Y) redoes — not while a picker is open.
  const keys = useRef({ save: () => {}, undo: doc.undo, redo: doc.redo, blocked: false })
  useEffect(() => {
    keys.current = { save: () => { if (dirty && !busy) save() }, undo: doc.undo, redo: doc.redo, blocked: !!picking }
  })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || keys.current.blocked) return
      const k = e.key.toLowerCase()
      if (k === 's') { e.preventDefault(); keys.current.save() }
      else if (k === 'z' && !e.shiftKey) { e.preventDefault(); keys.current.undo() }
      else if ((k === 'z' && e.shiftKey) || k === 'y') { e.preventDefault(); keys.current.redo() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (error && !issue) return <p role="alert" className="p-8 text-sm text-red-400">{error}</p>
  if (!issue || !current || !options) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  const saveLabel = !released ? 'Save' : drafts ? `Save and publish ${plural(drafts, 'draft', 'drafts')}` : 'Update'
  const inIssue = current.stories.map((s) => ({ id: s.post_id, title: info.get(s.post_id)?.title || 'A story' }))

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-5 py-3">
        <Link to={`/cappe/sites/${siteId}/issues`} onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
          className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"><ArrowLeft className="h-4 w-4" /> Issues</Link>
        <span className={`${ui.badge} ${released ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{released ? 'out' : 'draft'}</span>
        {issue.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
        <span className="text-xs text-zinc-500">{plural(current.stories.length, 'story', 'stories')}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button type="button" className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30"
            disabled={!doc.canUndo} onClick={doc.undo} aria-label="Undo" title={`Undo (${MOD}Z)`}><Undo2 className="h-4 w-4" /></button>
          <button type="button" className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30"
            disabled={!doc.canRedo} onClick={doc.redo} aria-label="Redo" title={`Redo (${isMac ? '⇧⌘Z' : 'Ctrl+Y'})`}><Redo2 className="h-4 w-4" /></button>
          {dirty && <span className="text-xs text-zinc-500">Unsaved</span>}
          <button type="button" className={ui.btnGhost} onClick={() => setPreviewOpen((v) => !v)} aria-pressed={previewOpen}>
            <Eye className="h-4 w-4" /> Preview
          </button>
          <button type="button" className={released ? ui.btnPrimary : ui.btnGhost} disabled={!!busy || !dirty} onClick={() => save()}
            title={`${saveLabel} (${MOD}S)`}>
            {busy === 'save' && <Loader2 className="h-4 w-4 animate-spin" />} {saveLabel}
          </button>
          {released
            ? <button type="button" className={ui.btnGhost} disabled={!!busy} onClick={withdraw}>
                {busy === 'withdraw' && <Loader2 className="h-4 w-4 animate-spin" />} Withdraw
              </button>
            : <button type="button" className={ui.btnPrimary} disabled={!!busy || !current.stories.length} onClick={release}
                title={current.stories.length ? undefined : 'Add a story first'}>
                {busy === 'release' && <Loader2 className="h-4 w-4 animate-spin" />} Release No. {current.number}
              </button>}
        </div>
      </header>
      {error && <p role="alert" className="border-b border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-300">{error}</p>}
      {note && <p className="border-b border-emerald-500/30 bg-emerald-500/10 px-5 py-2 text-sm text-emerald-300" aria-live="polite">{note}</p>}

      <div className={`grid flex-1 ${previewOpen ? 'lg:grid-cols-2' : ''}`}>
        <div className="space-y-4 overflow-y-auto p-5">
          <section className={`${ui.card} grid gap-3 p-4 sm:grid-cols-[7rem_1fr]`}>
            <label className="text-sm text-zinc-300">Number
              <input type="number" min={1} max={9999} value={current.number} aria-label="Issue number" className={`${ui.input} mt-1`}
                onChange={(e) => { const n = Number(e.target.value); if (Number.isInteger(n) && n >= 1 && n <= 9999) setDoc((d) => (d ? { ...d, number: n } : d)) }} />
            </label>
            <label className="text-sm text-zinc-300">Title <span className="text-zinc-500">(optional)</span>
              <input value={current.title} maxLength={120} placeholder="The tide issue" aria-label="Issue title" className={`${ui.input} mt-1`}
                onChange={(e) => setDoc((d) => (d ? { ...d, title: e.target.value } : d))} />
            </label>
          </section>

          <div className="flex gap-1" role="tablist" aria-label="Edit">
            {TABS.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${tab === t.key ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'stories' && (
            <IssueStories stories={current.stories} info={info} released={released} onChange={setStories}
              onRemove={(id) => setDoc((d) => (d ? removeStory(d, id) : d), { step: true })} onAdd={() => setPicking('stories')} />
          )}
          {tab === 'cover' && (
            <CoverPanel cover={current.cover} templates={options.templates} assets={assets} stories={inIssue} name={name || 'Magazine'}
              number={current.number} onChange={setCover} onPickPhoto={() => setPicking('photo')} />
          )}
          {tab === 'contents' && <ContentsPanel contents={current.contents} onChange={setContents} />}

          {!released && (
            <div className="pt-4">
              <button type="button" onClick={remove} className={`inline-flex items-center gap-2 text-sm ${ui.danger}`}>
                <Trash2 className="h-4 w-4" /> Delete issue
              </button>
            </div>
          )}
        </div>

        {previewOpen && (
          <div className="hidden border-l border-zinc-800 bg-zinc-950 lg:block">
            <BookFrame html={preview} title="Issue preview" keepPlace spread={tab === 'cover' ? 0 : tab === 'contents' ? 1 : undefined}
              className="sticky top-0 h-[calc(100dvh-3.9rem)]" />
          </div>
        )}
      </div>

      {picking === 'stories' && (
        <StoryPicker stories={posts} inIssue={new Set(current.stories.map((s) => s.post_id))} taken={taken}
          room={options.max_stories - current.stories.length} onClose={() => setPicking(null)}
          onAdd={(ids) => { setDoc((d) => (d ? addStories(d, ids) : d), { step: true }); setPicking(null) }} />
      )}
      {picking === 'photo' && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center" role="dialog" aria-label="Choose the cover photo">
          <div className={`${ui.card} max-h-[90vh] w-full max-w-5xl overflow-y-auto p-5`}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-100">Choose the cover photo</h2>
              <button type="button" onClick={() => setPicking(null)} className="text-zinc-500 hover:text-zinc-300" aria-label="Close picker"><X className="h-4 w-4" /></button>
            </div>
            <LibraryPanel siteId={siteId!} onPick={(a) => {
              setAssets((m) => new Map(m).set(a.id, a))
              setCover({ ...current.cover, photo: { ...current.cover.photo, asset_id: a.id } }, true)
              setPicking(null)
            }} />
          </div>
        </div>
      )}
    </div>
  )
}
