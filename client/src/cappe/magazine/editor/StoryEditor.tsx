import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Eye, Loader2, Plus, Trash2, Wand2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type {
  CappeAsset, CappePost, CappeStockSource, CappeStoryOptions, StoryBlock, StoryContent, StoryLayout,
} from '../../types'
import LibraryPanel from '../library/LibraryPanel'
import AssistPanel from './AssistPanel'
import BlockEditor from './BlockEditor'
import { BLOCK_LABELS, moveBlock, newBlock, withCaption, withText } from './blocks'

type Fields = { title: string; kicker: string; excerpt: string; byline: string; topic: string; layout: StoryLayout; status: CappePost['status'] }

const fieldsOf = (p: CappePost): Fields => ({
  title: p.title, kicker: p.kicker || '', excerpt: p.excerpt || '', byline: p.byline || '', topic: p.topic || '',
  layout: p.layout, status: p.status,
})

const ADDABLE: StoryBlock['type'][] = ['text', 'photo', 'photos', 'quote', 'sidebar', 'qa', 'divider']

/** `sites/:siteId/stories/:postId` — one story: its words, its blocks, and a
 *  live preview of the page the site will render. */
export default function StoryEditor() {
  const { siteId, postId } = useParams<{ siteId: string; postId: string }>()
  const navigate = useNavigate()
  const [post, setPost] = useState<CappePost | null>(null)
  const [fields, setFields] = useState<Fields | null>(null)
  const [blocks, setBlocks] = useState<StoryBlock[]>([])
  const [options, setOptions] = useState<CappeStoryOptions | null>(null)
  const [assets, setAssets] = useState<Map<string, CappeAsset>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [picking, setPicking] = useState<((a: CappeAsset) => void) | null>(null)
  const [adding, setAdding] = useState(false)
  const [assisting, setAssisting] = useState(false)
  const [finding, setFinding] = useState<{ source: CappeStockSource; query: string } | null>(null)
  const [preview, setPreview] = useState<string>('')
  const [previewOpen, setPreviewOpen] = useState(true)
  const previewGen = useRef(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      cappeApi.get<CappePost>(`/sites/${siteId}/posts/${postId}`),
      cappeApi.get<CappeStoryOptions>(`/sites/${siteId}/stories/options`),
      cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${siteId}/assets`),
    ]).then(([p, o, a]) => {
      if (cancelled) return
      setPost(p)
      setFields(fieldsOf(p))
      setBlocks(p.content?.blocks || [])
      setOptions(o)
      setAssets(new Map(a.assets.map((x) => [x.id, x])))
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load the story') })
    return () => { cancelled = true }
  }, [siteId, postId])

  const isStory = post?.format === 'blocks'
  const dirty = useMemo(() => {
    if (!post || !fields) return false
    return JSON.stringify(fields) !== JSON.stringify(fieldsOf(post))
      || JSON.stringify(blocks) !== JSON.stringify(post.content?.blocks || [])
  }, [post, fields, blocks])

  // The preview follows the editor, a moment after typing settles.
  useEffect(() => {
    if (!fields || !isStory || !previewOpen) return
    const gen = ++previewGen.current
    const t = setTimeout(() => {
      const body = { title: fields.title, excerpt: fields.excerpt || null, kicker: fields.kicker || null, topic: fields.topic || null,
        layout: fields.layout, byline: fields.byline || null, content: { blocks } satisfies StoryContent }
      cappeApi.postHtml(`/sites/${siteId}/stories/preview`, body)
        .then((html) => { if (gen === previewGen.current) setPreview(html) })
        .catch(() => { /* the last good preview stays up */ })
    }, 600)
    return () => clearTimeout(t)
  }, [siteId, fields, blocks, isStory, previewOpen])

  const setField = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((f) => (f ? { ...f, [key]: value } : f))

  const pickAsset = useCallback((done: (a: CappeAsset) => void) => {
    setPicking(() => (a: CappeAsset) => {
      setAssets((m) => new Map(m).set(a.id, a))
      done(a)
      setPicking(null)
    })
  }, [])

  const save = async (status?: CappePost['status']) => {
    if (!fields || !post) return
    setSaving(true)
    setError(null)
    const next = status ? { ...fields, status } : fields
    try {
      const body: Record<string, unknown> = {
        title: next.title.trim() || 'Untitled story', kicker: next.kicker.trim() || null, excerpt: next.excerpt.trim() || null,
        byline: next.byline.trim() || null, topic: next.topic || null, layout: next.layout, status: next.status,
      }
      if (isStory) {
        body.content = { blocks }
        const cover = blocks[0]?.type === 'cover' ? blocks[0].asset_id : null
        body.cover_asset_id = cover
      }
      const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${postId}`, body)
      setPost(updated)
      setFields(fieldsOf(updated))
      setBlocks(updated.content?.blocks || [])
      setSavedAt(Date.now())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  const becomeStory = async () => {
    setSaving(true)
    try {
      const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${postId}`, { format: 'blocks' })
      setPost(updated)
      setFields(fieldsOf(updated))
      setBlocks(updated.content?.blocks || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not convert this post')
    } finally {
      setSaving(false)
    }
  }

  const startFromLayout = (layout: StoryLayout) => {
    const starter = options?.layouts.find((l) => l.key === layout)
    setField('layout', layout)
    if (starter && blocks.every((b) => b.type === 'cover' ? !b.asset_id : b.type === 'text' ? !b.md : true)) {
      setBlocks(starter.content.blocks)
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this story? This can’t be undone.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}/posts/${postId}`)
      navigate(`/sites/${siteId}/stories`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete')
    }
  }

  if (error && !post) return <p role="alert" className="p-8 text-sm text-red-400">{error}</p>
  if (!post || !fields || !options) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-5 py-3">
        <Link to={`/sites/${siteId}/stories`} className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"><ArrowLeft className="h-4 w-4" /> Stories</Link>
        <span className={`${ui.badge} ${post.status === 'published' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{post.status}</span>
        {post.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
        <span className="text-xs text-zinc-500">{isStory ? `${post.reading_minutes || 0} min read · ${post.word_count} words` : 'Plain post'}</span>
        <div className="ml-auto flex items-center gap-2">
          {savedAt && !dirty && <span className="text-xs text-emerald-400">Saved</span>}
          {isStory && <button type="button" className={ui.btnGhost} onClick={() => setAssisting((v) => !v)} aria-pressed={assisting}><Wand2 className="h-4 w-4" /> Assist</button>}
          {isStory && <button type="button" className={ui.btnGhost} onClick={() => setPreviewOpen((v) => !v)} aria-pressed={previewOpen}><Eye className="h-4 w-4" /> Preview</button>}
          <button type="button" className={ui.btnGhost} disabled={saving || !dirty} onClick={() => save()}>Save</button>
          {post.status !== 'published'
            ? <button type="button" className={ui.btnPrimary} disabled={saving} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Publish</button>
            : <button type="button" className={ui.btnPrimary} disabled={saving || !dirty} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Update</button>}
        </div>
      </header>
      {error && <p role="alert" className="border-b border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-300">{error}</p>}

      <div className={`grid flex-1 ${previewOpen && isStory ? 'lg:grid-cols-2' : ''}`}>
        <div className="space-y-4 overflow-y-auto p-5">
          {assisting && isStory && (
            <AssistPanel siteId={siteId!} postId={postId!} title={fields.title} excerpt={fields.excerpt} blocks={blocks}
              assets={assets} onClose={() => setAssisting(false)}
              onHeadline={(h) => setFields((f) => (f ? { ...f, title: h.title, excerpt: h.dek || f.excerpt, kicker: h.kicker || f.kicker } : f))}
              onCaption={(id, caption) => setBlocks((bs) => withCaption(bs, id, caption))}
              onAlt={(a) => setAssets((m) => new Map(m).set(a.id, a))}
              onTighten={(i, md) => setBlocks((bs) => withText(bs, i, md))}
              onDraft={(d) => {
                setFields((f) => (f ? { ...f, title: d.title || f.title, excerpt: d.excerpt || f.excerpt, kicker: d.kicker || f.kicker } : f))
                setBlocks(d.content.blocks)
              }}
              onFind={setFinding} />
          )}
          <section className={`${ui.card} space-y-3 p-4`}>
            <input value={fields.title} onChange={(e) => setField('title', e.target.value)} maxLength={255} placeholder="Headline"
              className="w-full bg-transparent text-2xl font-semibold text-zinc-50 outline-none placeholder:text-zinc-600" aria-label="Headline" />
            <div className="grid gap-3 sm:grid-cols-2">
              <input value={fields.kicker} onChange={(e) => setField('kicker', e.target.value)} maxLength={60} placeholder="Kicker (the small line over the headline)" className={ui.input} aria-label="Kicker" />
              <input value={fields.byline} onChange={(e) => setField('byline', e.target.value)} maxLength={160} placeholder="Byline" className={ui.input} aria-label="Byline" />
            </div>
            <textarea value={fields.excerpt} onChange={(e) => setField('excerpt', e.target.value)} rows={2} maxLength={600}
              placeholder="Dek: one or two sentences that sell the story" className={ui.input} aria-label="Dek" />
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-sm text-zinc-300">Topic
                <select value={fields.topic} onChange={(e) => setField('topic', e.target.value)} className={`${ui.input} mt-1`}>
                  <option value="">None</option>
                  {options.topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </label>
              <label className="text-sm text-zinc-300">Layout
                <select value={fields.layout} onChange={(e) => startFromLayout(e.target.value as StoryLayout)} className={`${ui.input} mt-1`} disabled={!isStory}>
                  {options.layouts.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
              </label>
              <label className="text-sm text-zinc-300">Status
                <select value={fields.status} onChange={(e) => setField('status', e.target.value as CappePost['status'])} className={`${ui.input} mt-1`}>
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
            </div>
          </section>

          {!isStory ? (
            <section className={`${ui.card} space-y-3 p-4`}>
              <p className="text-sm text-zinc-300">This is a plain post written as Markdown. Turn it into a story to lay it out with pictures.</p>
              <textarea value={post.body || ''} readOnly rows={8} className={`${ui.input} font-mono text-[13px] opacity-80`} aria-label="Post body" />
              <button type="button" className={ui.btnPrimary} disabled={saving} onClick={becomeStory}>Turn into a story</button>
            </section>
          ) : (
            <>
              {blocks.map((b, i) => (
                <BlockEditor key={i} block={b} index={i} count={blocks.length} assets={assets}
                  onChange={(nb) => setBlocks((bs) => bs.map((x, j) => (j === i ? nb : x)))}
                  onMove={(d) => setBlocks((bs) => moveBlock(bs, i, i + d))}
                  onRemove={() => setBlocks((bs) => bs.filter((_, j) => j !== i))}
                  onPickAsset={pickAsset} />
              ))}
              <div className="relative">
                <button type="button" className={ui.btnGhost} onClick={() => setAdding((v) => !v)} aria-expanded={adding}><Plus className="h-4 w-4" /> Add a block</button>
                {adding && (
                  <div className="mt-2 flex flex-wrap gap-2" role="menu">
                    {blocks[0]?.type !== 'cover' && (
                      <button type="button" role="menuitem" className={ui.btnGhost} onClick={() => { setBlocks((bs) => [newBlock('cover'), ...bs]); setAdding(false) }}>Cover</button>
                    )}
                    {ADDABLE.map((t) => (
                      <button key={t} type="button" role="menuitem" className={ui.btnGhost} onClick={() => { setBlocks((bs) => [...bs, newBlock(t)]); setAdding(false) }}>{BLOCK_LABELS[t]}</button>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="pt-4">
            <button type="button" onClick={remove} className={`inline-flex items-center gap-2 text-sm ${ui.danger}`}><Trash2 className="h-4 w-4" /> Delete story</button>
          </div>
        </div>

        {previewOpen && isStory && (
          <div className="hidden border-l border-zinc-800 bg-zinc-950 lg:block">
            <iframe title="Story preview" srcDoc={preview} sandbox="allow-same-origin" className="h-full min-h-[80vh] w-full bg-white" />
          </div>
        )}
      </div>

      {(picking || finding) && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center" role="dialog"
          aria-label={picking ? 'Choose a picture' : 'Find pictures'}>
          <div className={`${ui.card} max-h-[90vh] w-full max-w-5xl overflow-y-auto p-5`}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-100">{picking ? 'Choose a picture' : 'Find pictures for this story'}</h2>
              <button type="button" onClick={() => { setPicking(null); setFinding(null) }} className="text-zinc-500 hover:text-zinc-300" aria-label="Close picker"><X className="h-4 w-4" /></button>
            </div>
            <LibraryPanel siteId={siteId!} onPick={picking || undefined} postId={postId}
              stockQuery={picking ? undefined : finding || undefined} />
          </div>
        </div>
      )}
    </div>
  )
}
