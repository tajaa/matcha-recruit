import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Eye, Loader2, Monitor, Redo2, Smartphone, Trash2, Undo2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import { useUnsavedGuard } from '../../pages/site/PageEditor/useUnsavedGuard'
import type {
  CappeAsset, CappeMagazine, CappeMagazineIssue, CappeMagazineIssueOptions, CappePost, ContentsDesign, CoverDesign,
  IssueStoryRef, StoryBlock,
} from '../../types'
import { confirmLeave } from '../../utils/unsavedGuard'
import { duplicateBlock, moveBlock } from '../editor/blocks'
import { useHistory } from '../editor/history'
import LibraryPanel from '../library/LibraryPanel'
import BookFrame from '../reader/BookFrame'
import BlockPanel, { PanelHead } from '../canvas/BlockPanel'
import EditFrame, { type Device } from '../canvas/EditFrame'
import type { CoverEl, FrameMessage, FrameTarget, Place } from '../canvas/bridge'
import { applyIssueEdit, coverFocal, moveCoverEl } from '../canvas/issueEdits'
import {
  sameStory, storyDocOf, storyFromMessage, storyPreviewBody, storyWordsBody, withPicture, type StoryDoc,
} from '../canvas/storyDoc'
import ContentsPanel from './ContentsPanel'
import CoverPanel, { CoverElementSection, CreditSection, PhotoSection, TemplateSection, type Selected } from './CoverPanel'
import IssueStories from './IssueStories'
import { addStories, docOf, pinStories, removeStory, saveBody, settleIssue, settleStories, type IssueDoc } from './issueDoc'
import StoryPicker from './StoryPicker'

type Tab = 'stories' | 'cover' | 'contents'
const TABS: { key: Tab; label: string }[] = [
  { key: 'stories', label: 'Stories' }, { key: 'cover', label: 'Cover' }, { key: 'contents', label: 'Contents' },
]
type View = 'page' | 'outline'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const MOD = isMac ? '⌘' : 'Ctrl+'
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

const COVER_NAMES: Record<string, string> = { masthead: 'Masthead', issue_line: 'Issue line', photo: 'Cover photo' }
const selectedOf = (el: CoverEl): Selected => (el === 'masthead' || el === 'issue_line' ? el : Number(el.slice(5)))

/** Two buttons, one of them on. */
function Toggle<T extends string>({ value, options, onChange, label }: {
  value: T; options: { key: T; label: string; icon?: ReactNode }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div className="flex rounded-lg border border-zinc-800 p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)} title={o.label}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${value === o.key ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}>
          {o.icon}{o.icon ? <span className="sr-only">{o.label}</span> : o.label}
        </button>
      ))}
    </div>
  )
}

/** `sites/:siteId/issues/:issueId` — one issue, edited on its pages as
 *  readers will turn them: the cover's words typed and dragged where they
 *  sit, the contents typed on the contents, and each story's words typed on
 *  its own pages. The Outline keeps the forms (stories and their order, the
 *  cover, the contents) beside a preview. Releasing it publishes its draft
 *  stories; a released issue stays editable and each save goes live. Saving
 *  saves every story changed on its pages, then the issue. */
export default function IssueEditor() {
  const { siteId, issueId } = useParams<{ siteId: string; issueId: string }>()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [issue, setIssue] = useState<CappeMagazineIssue | null>(null)
  const doc = useHistory<IssueDoc | null>(null)
  const { set: setDoc, reset: resetDoc, replace: replaceDoc } = doc
  const current = doc.value
  const [options, setOptions] = useState<CappeMagazineIssueOptions | null>(null)
  const [posts, setPosts] = useState<CappePost[]>([])
  const [assets, setAssets] = useState<Map<string, CappeAsset>>(new Map())
  const [name, setName] = useState('')
  const [tab, setTab] = useState<Tab>('stories')
  const [preview, setPreview] = useState('')
  const [previewOpen, setPreviewOpen] = useState(true)
  const [picking, setPicking] = useState<'photo' | 'stories' | ((a: CappeAsset) => void) | null>(null)
  const [busy, setBusy] = useState<'' | 'save' | 'release' | 'withdraw'>('')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const previewGen = useRef(0)
  const [view, setView] = useState<View>(params.get('view') === 'outline' ? 'outline' : 'page')
  const [device, setDevice] = useState<Device>('spread')
  const [asReader, setAsReader] = useState(false)
  const [page, setPage] = useState('')
  const [pageError, setPageError] = useState<string | null>(null)
  const [place, setPlace] = useState<Place>({ target: null, spread: 0 })
  const [typing, setTyping] = useState(false)
  const pageGen = useRef(0)

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
  const excerpts = useMemo(() => new Map(posts.map((p) => [p.id, p.excerpt])), [posts])
  const taken = useMemo(() => new Map((options?.taken || []).filter((t) => t.issue_id !== issueId)
    .map((t) => [t.post_id, t.number])), [options, issueId])
  const issueDirty = useMemo(() => !!issue && !!current
    && JSON.stringify(saveBody(current)) !== JSON.stringify(saveBody(docOf(issue))), [issue, current])
  // The stories changed on the issue's pages and not saved yet.
  const changed = useMemo(() => Object.entries(current?.drafts || {}).filter(([id, d]) => {
    const p = info.get(id)
    return p && current?.stories.some((s) => s.post_id === id) && !sameStory(d, storyDocOf(p))
  }).map(([id]) => id), [current, info])
  const dirty = issueDirty || changed.length > 0
  const drafts = (current?.stories || []).filter((s) => info.get(s.post_id)?.status === 'draft').length
  const released = issue?.status === 'released'
  const onPage = view === 'page'
  const pageStories = useMemo<ReadonlySet<string>>(() => new Set((current?.stories || []).map((s) => s.post_id)),
    [current?.stories])

  /** What the server renders the issue from: the issue, and each changed
   *  story's unsaved words. */
  const previewBody = useCallback((d: IssueDoc, edit: boolean) => {
    const stories_content: Record<string, ReturnType<typeof storyPreviewBody>> = {}
    for (const [id, sd] of Object.entries(d.drafts || {})) {
      if (d.stories.some((s) => s.post_id === id)) stories_content[id] = storyPreviewBody(sd)
    }
    return { issue_id: issueId, ...saveBody(d), edit, stories_content }
  }, [issueId])

  // The preview follows the editor, a moment after a change settles.
  const wantPreview = onPage ? asReader : previewOpen
  useEffect(() => {
    if (!current || !wantPreview) return
    const gen = ++previewGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/magazine/issues/preview`, previewBody(current, false))
        .then((html) => { if (gen === previewGen.current) setPreview(html) })
        .catch(() => { /* the last good preview stays up */ })
    }, 600)
    return () => clearTimeout(t)
  }, [siteId, current, wantPreview, previewBody])

  // The pages to edit on: set again after each change, never while words
  // are typed on them (they are already there).
  useEffect(() => {
    if (!current || !onPage || asReader || typing) return
    const gen = ++pageGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/magazine/issues/preview`, previewBody(current, true))
        .then((html) => { if (gen === pageGen.current) { setPage(html); setPageError(null) } })
        .catch((e) => { if (gen === pageGen.current) setPageError(e instanceof Error ? e.message : 'Could not show the pages') })
    }, 250)
    return () => clearTimeout(t)
  }, [siteId, current, onPage, asReader, typing, previewBody])

  const setStories = useCallback((stories: IssueStoryRef[], step = false) =>
    setDoc((d) => (d ? { ...d, stories } : d), { step }), [setDoc])
  const setCover = useCallback((cover: CoverDesign, step = false) => setDoc((d) => (d ? { ...d, cover } : d), { step }), [setDoc])
  const setContents = useCallback((contents: ContentsDesign, step = false) =>
    setDoc((d) => (d ? { ...d, contents } : d), { step }), [setDoc])

  /** A story of the issue as edited here: its unsaved draft, else as saved. */
  const storyOf = (d: IssueDoc | null, id: string): StoryDoc | null => {
    const p = info.get(id)
    return d?.drafts?.[id] ?? (p && p.format === 'blocks' ? storyDocOf(p) : null)
  }
  const setStory = (id: string, change: (s: StoryDoc) => StoryDoc, step = false) =>
    setDoc((d) => {
      const s = storyOf(d, id)
      if (!d || !s) return d
      const next = change(s)
      return next === s ? d : { ...d, drafts: { ...d.drafts, [id]: next } }
    }, { step })

  /** What the server sent back after a save or release; drafts it published
   *  are published here too. Story drafts still unsaved are kept. */
  const took = (updated: CappeMagazineIssue, keep: Record<string, StoryDoc> = {}) => {
    setIssue(updated)
    replaceDoc({ ...docOf(updated), ...(Object.keys(keep).length ? { drafts: keep } : {}) })
    published(updated)
  }
  /** Drafts the server published with the issue are published here too. */
  const published = (updated: CappeMagazineIssue) => {
    if (!updated.published.length) return
    const ids = new Set(updated.stories.map((s) => s.post_id))
    setPosts((ps) => ps.map((p) => (ids.has(p.id) && p.status === 'draft' ? { ...p, status: 'published' } : p)))
    setNote(`Published with the issue: ${updated.published.join(', ')}.`)
  }

  const save = async (): Promise<boolean> => {
    if (!current || !issue) return false
    setBusy('save')
    setError(null)
    setNote(null)
    const sent = current
    const ids = changed
    // Each story as saved before, for the undo steps that still show it.
    const before: Record<string, StoryDoc> = {}
    for (const id of ids) {
      const p = info.get(id)
      if (p?.format === 'blocks') before[id] = storyDocOf(p)
    }
    try {
      // Each story changed on its pages first: a released issue's save
      // publishes the draft stories in it, and must publish these words,
      // not the ones stored before.
      const failed: string[] = []
      const failedIds: string[] = []
      const savedPosts: CappePost[] = []
      for (const id of ids) {
        const d = sent.drafts![id]
        try {
          savedPosts.push(await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${id}`, storyWordsBody(d)))
        } catch (e) {
          failedIds.push(id)
          failed.push(`“${d.fields.title || info.get(id)?.title || 'A story'}” (${e instanceof Error ? e.message : 'not saved'})`)
        }
      }
      if (savedPosts.length) {
        const byId = new Map(savedPosts.map((p) => [p.id, p]))
        setPosts((ps) => ps.map((p) => byId.get(p.id) ?? p))
        const saved = new Set(byId.keys())
        const pinned = Object.fromEntries(Object.entries(before).filter(([id]) => saved.has(id)))
        doc.map((d, present) => (d ? (present ? settleStories(d, sent, saved) : pinStories(d, pinned)) : d))
      }
      // Saving the issue would publish a draft story whose new words didn't
      // save: it waits, so the old words never go out.
      const held = issueDirty && released && failedIds.some((id) => info.get(id)?.status === 'draft')
      if (issueDirty && !held) {
        const saved = await cappeApi.put<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues/${issueId}`, saveBody(sent))
        setIssue(saved)
        doc.map((d, present) => (d && present ? settleIssue(d, sent, docOf(saved)) : d))
        published(saved)
      }
      if (failed.length) {
        setError(`Not saved: ${failed.join('; ')}. ${failed.length === 1 ? 'It is' : 'They are'} still here to save again.`
          + (held ? ' The issue waits for it, so nothing is published with its old words.' : ''))
        return false
      }
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
      took(await cappeApi.post<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues/${issueId}/withdraw`), current?.drafts)
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
  // On the pages they come from the page itself (`mz-key`).
  const keys = useRef({ save: () => {}, undo: doc.undo, redo: doc.redo, blocked: false })
  useEffect(() => {
    keys.current = { save: () => { if (dirty && !busy) save() }, undo: doc.undo, redo: doc.redo, blocked: !!picking }
  })
  // ⌘S on the page arrives right after the words typed there: the save runs
  // once a render has those words in the document, not from this render's.
  const [saveAsked, setSaveAsked] = useState(0)
  useEffect(() => { if (saveAsked) keys.current.save() }, [saveAsked])
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

  const select = (target: FrameTarget | null) => setPlace((p) => ({ ...p, target }))
  const removeBlock = (story: string, i: number) => {
    setStory(story, (s) => ({ ...s, blocks: s.blocks.filter((_, j) => j !== i) }), true)
    select(null)
  }

  /** What the pages say: a selection, words typed, a block added, a picture
   *  to choose, something dragged, a key. */
  const onFrame = (msg: FrameMessage) => {
    if (!current) return
    switch (msg.type) {
      case 'mz-select': select(msg.target.kind === 'none' ? null : msg.target); return
      case 'mz-place': setPlace((p) => (p.spread === msg.spread ? p : { ...p, spread: msg.spread })); return
      case 'mz-editing': setTyping(msg.on); return
      case 'mz-key': {
        if (keys.current.blocked) return
        const t = place.target
        if (msg.key === 'save') setSaveAsked((n) => n + 1)
        else if (msg.key === 'undo') doc.undo()
        else if (msg.key === 'redo') doc.redo()
        // Not a story's cover: it is its header (see StoryEditor).
        else if (t?.kind === 'block' && storyOf(current, t.story)?.blocks[t.block]
          && storyOf(current, t.story)?.blocks[t.block].type !== 'cover') removeBlock(t.story, t.block)
        return
      }
      case 'mz-pick': {
        const { story, block, item } = msg
        if (!storyOf(current, story)?.blocks[block]) return
        select({ kind: 'block', story, block })
        setPicking(() => (a: CappeAsset) => {
          setAssets((m) => new Map(m).set(a.id, a))
          setStory(story, (s) => ({ ...s, blocks: s.blocks.map((b, i) => (i === block ? withPicture(b, a.id, item) : b)) }), true)
          setPicking(null)
        })
        return
      }
      case 'mz-edit':
        if (msg.field.startsWith('issue:')) {
          // The issue's own words are plain (the bridge sends no document for them).
          const words = msg.rich ? null : msg.value
          if (words !== null && applyIssueEdit(current, msg.field, words, excerpts)) {
            setDoc((d) => (d ? applyIssueEdit(d, msg.field, words, excerpts) ?? d : d))
          }
          return
        }
        break
      case 'mz-move':
        if (msg.target.kind === 'cover') {
          const el = msg.target.el
          if (moveCoverEl(current.cover, el, msg.x, msg.y, msg.w)) {
            setDoc((d) => (d ? { ...d, cover: moveCoverEl(d.cover, el, msg.x, msg.y, msg.w) ?? d.cover } : d), { step: true })
          }
          return
        }
        break
      case 'mz-focal':
        if (msg.target.kind === 'cover') {
          setDoc((d) => (d ? { ...d, cover: coverFocal(d.cover, msg.x, msg.y) } : d), { step: true })
          return
        }
        break
      default:
        break
    }
    // The rest is about one story's words or blocks.
    const id = 'story' in msg ? msg.story : msg.type === 'mz-move' && msg.target.kind === 'overlay' ? msg.target.story
      : msg.type === 'mz-focal' && msg.target.kind === 'block' ? msg.target.story : null
    const s = id ? storyOf(current, id) : null
    const r = s && id ? storyFromMessage(s, msg) : null
    if (!r || !id) return
    setStory(id, (sd) => storyFromMessage(sd, msg)?.doc ?? sd, r.step)
    if (r.select !== undefined) select({ kind: 'block', story: id, block: r.select })
  }

  if (error && !issue) return <p role="alert" className="p-8 text-sm text-red-400">{error}</p>
  if (!issue || !current || !options) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  const saveLabel = !released ? 'Save' : drafts ? `Save and publish ${plural(drafts, 'draft', 'drafts')}` : 'Update'
  const inIssue = current.stories.map((s) => ({ id: s.post_id, title: info.get(s.post_id)?.title || 'A story' }))
  const coverProps = { cover: current.cover, onChange: setCover }

  const settings = (
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
  )
  const storyList = (
    <IssueStories stories={current.stories} info={info} released={released} onChange={setStories}
      onRemove={(id) => setDoc((d) => (d ? removeStory(d, id) : d), { step: true })} onAdd={() => setPicking('stories')} />
  )

  /** The panel beside the pages: whatever is selected on them. */
  const panel = (() => {
    const t = place.target
    if (t?.kind === 'cover' && t.el === 'photo') {
      return (
        <div>
          <PanelHead title="Cover photo" onClose={() => select(null)} />
          <div className="space-y-4 p-4">
            <PhotoSection {...coverProps} assets={assets} onPickPhoto={() => setPicking('photo')} focusHint />
            <TemplateSection {...coverProps} templates={options.templates} name={name || 'Magazine'} />
            <CreditSection {...coverProps} />
          </div>
        </div>
      )
    }
    if (t?.kind === 'cover') {
      const which = selectedOf(t.el)
      if (typeof which === 'number' && !current.cover.lines[which]) return null
      return (
        <div>
          <PanelHead title={COVER_NAMES[t.el] || `Cover line ${(which as number) + 1}`} onClose={() => select(null)} />
          <div className="space-y-3 p-4">
            <p className="text-xs text-zinc-500">Type its words on the cover; drag the round handle to move it, the bar to widen it.</p>
            <CoverElementSection {...coverProps} which={which} stories={inIssue} name={name || 'Magazine'} number={current.number}
              words={false} onRemoveLine={(i) => { setCover({ ...current.cover, lines: current.cover.lines.filter((_, j) => j !== i) }, true); select(null) }} />
          </div>
        </div>
      )
    }
    if (t?.kind === 'contents') {
      return (
        <div>
          <PanelHead title="Contents" onClose={() => select(null)} />
          <div className="space-y-3 p-4">
            <p className="text-xs text-zinc-500">Type the heading, the section names and each story’s line on the page.</p>
            <ContentsPanel contents={current.contents} onChange={setContents} />
          </div>
        </div>
      )
    }
    if (t?.kind === 'block') {
      const s = storyOf(current, t.story)
      const b = s?.blocks[t.block]
      if (s && b) {
        const setBlocks = (fn: (bs: StoryBlock[]) => StoryBlock[], step = false) => setStory(t.story, (sd) => ({ ...sd, blocks: fn(sd.blocks) }), step)
        return (
          <div>
            <p className="truncate border-b border-zinc-800 px-4 pt-3 text-[11px] text-zinc-500">In “{s.fields.title || 'a story'}”</p>
            <BlockPanel block={b} index={t.block} count={s.blocks.length} assets={assets}
              onChange={(nb) => setBlocks((bs) => bs.map((x, j) => (j === t.block ? nb : x)))}
              onMove={(dlt) => {
                const next = moveBlock(s.blocks, t.block, t.block + dlt)
                if (next === s.blocks) return
                setBlocks(() => next, true)
                select({ kind: 'block', story: t.story, block: t.block + dlt })
              }}
              onDuplicate={() => setBlocks((bs) => duplicateBlock(bs, t.block), true)}
              onRemove={() => removeBlock(t.story, t.block)}
              onPickAsset={(done) => setPicking(() => (a: CappeAsset) => { setAssets((m) => new Map(m).set(a.id, a)); done(a); setPicking(null) })}
              onClose={() => select(null)} />
          </div>
        )
      }
    }
    return (
      <div>
        <PanelHead title="The issue" />
        <div className="space-y-4 p-4">
          <p className="text-xs leading-relaxed text-zinc-500">
            Click anything on the pages to change it: the cover’s words and photo, the contents, and every story’s words
            on its own pages. Saving saves the issue and each story you changed here.
          </p>
          {settings}
          {storyList}
          {!released && (
            <button type="button" onClick={remove} className={`inline-flex items-center gap-2 text-sm ${ui.danger}`}>
              <Trash2 className="h-4 w-4" /> Delete issue
            </button>
          )}
        </div>
      </div>
    )
  })()

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-5 py-3">
        <Link to={`/cappe/sites/${siteId}/issues`} onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
          className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"><ArrowLeft className="h-4 w-4" /> Issues</Link>
        <span className={`${ui.badge} ${released ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{released ? 'out' : 'draft'}</span>
        {issue.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
        <span className="text-xs text-zinc-500">{plural(current.stories.length, 'story', 'stories')}</span>
        <Toggle label="Edit on" value={view} onChange={setView}
          options={[{ key: 'page', label: 'Pages' }, { key: 'outline', label: 'Outline' }]} />
        {onPage && (
          <>
            <Toggle label="Size" value={device} onChange={setDevice} options={[
              { key: 'spread', label: 'Two pages, as on a computer', icon: <Monitor className="h-4 w-4" /> },
              { key: 'phone', label: 'A phone', icon: <Smartphone className="h-4 w-4" /> },
            ]} />
            <label className="flex items-center gap-1.5 text-xs text-zinc-400" title="The issue as a reader sees it, paywalls and all">
              <input type="checkbox" checked={asReader} onChange={(e) => setAsReader(e.target.checked)} /> As a reader
            </label>
          </>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button type="button" className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30"
            disabled={!doc.canUndo} onClick={doc.undo} aria-label="Undo" title={`Undo (${MOD}Z)`}><Undo2 className="h-4 w-4" /></button>
          <button type="button" className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30"
            disabled={!doc.canRedo} onClick={doc.redo} aria-label="Redo" title={`Redo (${isMac ? '⇧⌘Z' : 'Ctrl+Y'})`}><Redo2 className="h-4 w-4" /></button>
          {dirty && (
            <span className="text-xs text-zinc-500">
              Unsaved{changed.length ? ` (${changed.length === 1 ? 'and a story' : `and ${changed.length} stories`})` : ''}
            </span>
          )}
          {!onPage && (
            <button type="button" className={ui.btnGhost} onClick={() => setPreviewOpen((v) => !v)} aria-pressed={previewOpen}>
              <Eye className="h-4 w-4" /> Preview
            </button>
          )}
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

      {onPage ? (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="relative h-[calc(100dvh-3.9rem)] min-h-[32rem] bg-zinc-950">
            {pageError && !asReader && (
              <p role="alert" className="absolute inset-x-0 top-0 z-10 bg-red-500/90 px-4 py-2 text-sm text-white">
                The pages couldn’t be set with the last change: {pageError}
              </p>
            )}
            {asReader
              ? <BookFrame html={preview} title="The issue as a reader sees it" keepPlace className="h-full" />
              : <EditFrame html={page} place={place} stories={pageStories} device={device} title="The issue's pages, to edit"
                  onMessage={onFrame} />}
          </div>
          <aside className="overflow-y-auto border-l border-zinc-800 bg-zinc-950/60 lg:h-[calc(100dvh-3.9rem)]" aria-label="Selected">
            {panel}
          </aside>
        </div>
      ) : (
        <div className={`grid flex-1 ${previewOpen ? 'lg:grid-cols-2' : ''}`}>
          <div className="space-y-4 overflow-y-auto p-5">
            {settings}

            <div className="flex gap-1" role="tablist" aria-label="Edit">
              {TABS.map((t) => (
                <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${tab === t.key ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}>
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'stories' && storyList}
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
      )}

      {picking === 'stories' && (
        <StoryPicker stories={posts} inIssue={new Set(current.stories.map((s) => s.post_id))} taken={taken}
          room={options.max_stories - current.stories.length} onClose={() => setPicking(null)}
          onAdd={(ids) => { setDoc((d) => (d ? addStories(d, ids) : d), { step: true }); setPicking(null) }} />
      )}
      {picking && picking !== 'stories' && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center" role="dialog"
          aria-label={picking === 'photo' ? 'Choose the cover photo' : 'Choose a picture'}>
          <div className={`${ui.card} max-h-[90vh] w-full max-w-5xl overflow-y-auto p-5`}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-100">{picking === 'photo' ? 'Choose the cover photo' : 'Choose a picture'}</h2>
              <button type="button" onClick={() => setPicking(null)} className="text-zinc-500 hover:text-zinc-300" aria-label="Close picker"><X className="h-4 w-4" /></button>
            </div>
            <LibraryPanel siteId={siteId!} onPick={picking === 'photo' ? (a) => {
              setAssets((m) => new Map(m).set(a.id, a))
              setCover({ ...current.cover, photo: { ...current.cover.photo, asset_id: a.id } }, true)
              setPicking(null)
            } : picking} />
          </div>
        </div>
      )}
    </div>
  )
}
