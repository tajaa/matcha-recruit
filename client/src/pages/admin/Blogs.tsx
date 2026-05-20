import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../../api/client'
import { Pencil, Plus, Trash2, ExternalLink, Check, X, Loader2, ArrowLeft } from 'lucide-react'

type BlogStatus = 'draft' | 'published' | 'archived'

type BlogPost = {
  id: string
  title: string
  slug: string
  content: string
  excerpt: string | null
  cover_image: string | null
  status: BlogStatus
  tags: string[]
  meta_title: string | null
  meta_description: string | null
  published_at: string | null
  created_at: string
  updated_at: string
  author_name?: string
  likes_count?: number
  submitted_for_review?: boolean
  submitted_at?: string | null
  source_project_id?: string | null
  review_notes?: string | null
}

type BlogList = { items: BlogPost[]; total: number }

const STATUS_FILTERS: Array<BlogStatus | 'all' | 'pending'> = ['all', 'pending', 'draft', 'published', 'archived']

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 80)
}

type AdminTab = 'posts' | 'comments'

type PendingComment = {
  id: string
  post_id: string
  user_id: string | null
  author_name: string
  content: string
  status: 'pending' | 'approved' | 'rejected' | 'spam'
  created_at: string
  post_title?: string | null
}

export default function Blogs() {
  const navigate = useNavigate()
  const location = useLocation()

  const initialTab: AdminTab =
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('tab') === 'comments'
      ? 'comments'
      : 'posts'
  const [tab, setTab] = useState<AdminTab>(initialTab)
  const [pendingCount, setPendingCount] = useState<number>(0)

  const [posts, setPosts] = useState<BlogPost[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<BlogStatus | 'all' | 'pending'>('all')
  const [editing, setEditing] = useState<BlogPost | null>(null)

  // Composer state
  const [composeId, setComposeId] = useState<string | null>(null)
  const [composeTitle, setComposeTitle] = useState('')
  const [composeSlug, setComposeSlug] = useState('')
  const [composeContent, setComposeContent] = useState('')
  const [composeExcerpt, setComposeExcerpt] = useState('')
  const [composeCover, setComposeCover] = useState('')
  const [composeTags, setComposeTags] = useState('')
  const [composeMetaTitle, setComposeMetaTitle] = useState('')
  const [composeMetaDesc, setComposeMetaDesc] = useState('')
  const [autoSlug, setAutoSlug] = useState(true)
  const [isDirty, setIsDirty] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  const [composeSaving, setComposeSaving] = useState(false)

  const isComposer = location.pathname.endsWith('/composer')

  // Sync with /composer route
  useEffect(() => {
    if (isComposer) {
      setComposeId(null)
      setComposeTitle(''); setComposeSlug(''); setComposeContent('')
      setComposeExcerpt(''); setComposeCover(''); setComposeTags('')
      setComposeMetaTitle(''); setComposeMetaDesc('')
      setAutoSlug(true)
      setIsDirty(false); setSaveStatus('saved')
    }
  }, [location.pathname])

  // Auto-slug
  useEffect(() => {
    if (autoSlug && isComposer) setComposeSlug(slugify(composeTitle))
  }, [composeTitle, autoSlug, isComposer])

  // Auto-save: 2s after last change
  useEffect(() => {
    if (!isDirty || !isComposer) return
    if (!composeTitle.trim()) return
    setSaveStatus('saving')
    const timer = window.setTimeout(async () => {
      try {
        const tags = composeTags.split(',').map(t => t.trim()).filter(Boolean)
        const body = {
          title: composeTitle.trim(),
          slug: composeSlug.trim() || slugify(composeTitle),
          content: composeContent,
          excerpt: composeExcerpt || null,
          cover_image: composeCover || null,
          status: 'draft' as BlogStatus,
          tags,
          meta_title: composeMetaTitle || null,
          meta_description: composeMetaDesc || null,
        }
        if (!composeId) {
          const created = await api.post<BlogPost>('/blogs', body)
          setComposeId(created.id)
          setPosts(prev => prev.some(p => p.id === created.id) ? prev : [created, ...prev])
        } else {
          const updated = await api.put<BlogPost>(`/blogs/${composeId}`, body)
          setPosts(prev => prev.map(p => p.id === updated.id ? updated : p))
        }
        setIsDirty(false)
        setSaveStatus('saved')
      } catch {
        setSaveStatus('unsaved')
      }
    }, 2000)
    return () => window.clearTimeout(timer)
  }, [composeTitle, composeSlug, composeContent, composeExcerpt, composeCover, composeTags, composeMetaTitle, composeMetaDesc, isDirty])

  // Unsaved-changes guard
  useEffect(() => {
    function handler(e: BeforeUnloadEvent) {
      if (isDirty) { e.preventDefault(); e.returnValue = '' }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  useEffect(() => {
    api.get<PendingComment[]>('/blogs/comments/pending')
      .then(rows => setPendingCount(rows.length))
      .catch(() => setPendingCount(0))
  }, [])

  async function load() {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: '1', limit: '100' })
      if (filter === 'pending') {
        params.set('pending_review', 'true')
      } else if (filter !== 'all') {
        params.set('status', filter)
      }
      const data = await api.get<BlogList>(`/blogs?${params}`)
      setPosts(data.items)
    } catch (err) {
      console.error('Load blogs failed', err)
    } finally {
      setLoading(false)
    }
  }

  async function approve(p: BlogPost) {
    try {
      await api.put(`/blogs/${p.id}`, { status: 'published', submitted_for_review: false })
      await load()
    } catch (err) {
      alert(`Approve failed: ${(err as Error).message}`)
    }
  }

  async function reject(p: BlogPost) {
    const notes = prompt('Rejection notes (optional):', '')
    if (notes === null) return
    try {
      await api.put(`/blogs/${p.id}`, { submitted_for_review: false, review_notes: notes || null })
      await load()
    } catch (err) {
      alert(`Reject failed: ${(err as Error).message}`)
    }
  }

  useEffect(() => { load() }, [filter])

  async function deletePost(id: string) {
    if (!confirm('Delete this post permanently?')) return
    try {
      await api.delete(`/blogs/${id}`)
      setPosts(prev => prev.filter(p => p.id !== id))
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`)
    }
  }

  async function publishCompose() {
    if (!composeTitle.trim()) { alert('Title required.'); return }
    setComposeSaving(true)
    try {
      const tags = composeTags.split(',').map(t => t.trim()).filter(Boolean)
      const body = {
        title: composeTitle.trim(),
        slug: composeSlug.trim() || slugify(composeTitle),
        content: composeContent,
        excerpt: composeExcerpt || null,
        cover_image: composeCover || null,
        status: 'published' as BlogStatus,
        tags,
        meta_title: composeMetaTitle || null,
        meta_description: composeMetaDesc || null,
      }
      if (!composeId) {
        await api.post<BlogPost>('/blogs', body)
      } else {
        await api.put<BlogPost>(`/blogs/${composeId}`, body)
      }
      setIsDirty(false); setSaveStatus('saved')
      navigate('/admin/blogs')
      load()
    } catch (err) {
      alert(`Publish failed: ${(err as Error).message}`)
    }
    setComposeSaving(false)
  }

  async function uploadCover(file: File) {
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await api.upload<{ url: string }>('/blogs/upload', fd)
      setComposeCover(res.url)
      mark()
    } catch (err) {
      alert(`Upload failed: ${(err as Error).message}`)
    }
  }

  function mark() { setIsDirty(true); setSaveStatus('unsaved') }

  const draftCount = posts.filter(p => p.status === 'draft').length

  // ── Composer view ────────────────────────────────────────────────────────
  if (isComposer) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => {
              if (isDirty && !confirm('Discard unsaved changes?')) return
              navigate('/admin/blogs')
            }}
            className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1 text-xs"
          >
            <ArrowLeft size={14} /> Posts
          </button>
          <span className="text-zinc-700">/</span>
          <span className="text-xs text-zinc-400">New post</span>
          <div className="ml-auto h-4 flex items-center">
            {saveStatus === 'saving' && <span className="text-[10px] text-zinc-500 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving…</span>}
            {saveStatus === 'saved' && composeId && <span className="text-[10px] text-zinc-500">Draft saved</span>}
            {saveStatus === 'unsaved' && <span className="text-[10px] text-amber-500">Unsaved changes</span>}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Title</label>
            <input
              type="text"
              value={composeTitle}
              onChange={e => { setComposeTitle(e.target.value); mark() }}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-lg text-zinc-100 mt-1 font-semibold"
              placeholder="Post title…"
              autoFocus
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 flex items-center justify-between">
              <span>Slug (/blog/&lt;slug&gt;)</span>
              <label className="flex items-center gap-1 normal-case text-zinc-400 font-normal cursor-pointer">
                <input type="checkbox" checked={autoSlug} onChange={e => setAutoSlug(e.target.checked)} />
                <span>Auto from title</span>
              </label>
            </label>
            <input
              type="text"
              value={composeSlug}
              onChange={e => { setComposeSlug(slugify(e.target.value)); setAutoSlug(false); mark() }}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono mt-1"
              placeholder="my-post-slug"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Excerpt (optional, ~160 chars)</label>
            <textarea
              value={composeExcerpt}
              onChange={e => { setComposeExcerpt(e.target.value); mark() }}
              rows={2}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1 resize-none"
              placeholder="One-line summary shown on blog index"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Cover image</label>
            <div className="flex items-center gap-2 mt-1">
              <input
                type="text"
                value={composeCover}
                onChange={e => { setComposeCover(e.target.value); mark() }}
                className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono"
                placeholder="https://…"
              />
              <label className="bg-zinc-800 hover:bg-zinc-700 px-3 py-2 text-xs text-zinc-300 rounded cursor-pointer">
                Upload
                <input type="file" accept="image/*" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) uploadCover(f) }} />
              </label>
            </div>
            {composeCover && <img src={composeCover} alt="cover preview" className="mt-2 h-32 object-cover rounded border border-zinc-800" />}
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Content (markdown)</label>
              <label className="text-[10px] text-zinc-400 hover:text-zinc-200 cursor-pointer">
                Insert image
                <input type="file" accept="image/*" className="hidden" onChange={async e => {
                  const f = e.target.files?.[0]; if (!f) return
                  const fd = new FormData(); fd.append('file', f)
                  try {
                    const res = await api.upload<{ url: string }>('/blogs/upload', fd)
                    setComposeContent(c => `${c}\n\n![${f.name}](${res.url})\n`)
                    mark()
                  } catch {}
                }} />
              </label>
            </div>
            <textarea
              value={composeContent}
              onChange={e => { setComposeContent(e.target.value); mark() }}
              rows={20}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono"
              placeholder={'# Heading\n\nParagraph text…'}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Tags (comma-separated)</label>
              <input
                type="text"
                value={composeTags}
                onChange={e => { setComposeTags(e.target.value); mark() }}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
                placeholder="hr, compliance"
              />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta title (SEO)</label>
              <input
                type="text"
                value={composeMetaTitle}
                onChange={e => { setComposeMetaTitle(e.target.value); mark() }}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta description (SEO)</label>
            <input
              type="text"
              value={composeMetaDesc}
              onChange={e => { setComposeMetaDesc(e.target.value); mark() }}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={publishCompose}
              disabled={composeSaving || !composeTitle.trim()}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium rounded"
            >
              {composeSaving ? 'Publishing…' : 'Publish'}
            </button>
            <button
              onClick={() => { if (isDirty && !confirm('Discard unsaved changes?')) return; navigate('/admin/blogs') }}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
            >
              Back to drafts
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Posts list view ──────────────────────────────────────────────────────
  const drafts = posts.filter(p => p.status === 'draft')
  const nonDrafts = posts.filter(p => p.status !== 'draft')

  const PostRow = ({ p }: { p: BlogPost }) => (
    <tr className="border-t border-zinc-800 hover:bg-zinc-900/40">
      <td className="px-3 py-2 text-zinc-100">{p.title}</td>
      <td className="px-3 py-2 text-zinc-500 font-mono text-xs">{p.slug}</td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-1.5">
          <span className={`text-[10px] px-2 py-0.5 rounded uppercase tracking-wider font-mono ${
            p.status === 'published' ? 'bg-emerald-900/40 text-emerald-400'
            : p.status === 'draft' ? 'bg-zinc-800 text-zinc-400'
            : 'bg-zinc-900 text-zinc-600'
          }`}>{p.status}</span>
          {p.submitted_for_review && (
            <span className="text-[10px] px-2 py-0.5 rounded uppercase tracking-wider font-mono bg-amber-900/40 text-amber-400">review</span>
          )}
        </div>
      </td>
      <td className="px-3 py-2 text-zinc-500 text-xs">{new Date(p.updated_at).toLocaleDateString()}</td>
      <td className="px-3 py-2 text-right">
        <div className="flex justify-end gap-2">
          {p.submitted_for_review && (
            <>
              <button onClick={() => approve(p)} className="text-emerald-400 hover:text-emerald-300 text-xs font-medium px-2 py-0.5 rounded border border-emerald-900/60">Approve</button>
              <button onClick={() => reject(p)} className="text-amber-400 hover:text-amber-300 text-xs font-medium px-2 py-0.5 rounded border border-amber-900/60">Reject</button>
            </>
          )}
          {p.status === 'published' && (
            <a href={`/blog/${p.slug}`} target="_blank" rel="noreferrer" className="text-zinc-500 hover:text-zinc-300" title="View on site">
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
          <button onClick={() => { setEditing(p) }} className="text-zinc-500 hover:text-zinc-300" title="Edit">
            <Pencil className="w-4 h-4" />
          </button>
          <button onClick={() => deletePost(p.id)} className="text-zinc-500 hover:text-red-400" title="Delete">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Blog</h1>
          <p className="text-xs text-zinc-500 mt-1">Posts publish to the public landing page at /blog.</p>
        </div>
        {tab === 'posts' && (
          <button
            onClick={() => navigate('/admin/blogs/composer')}
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-2 rounded text-sm font-medium flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> New post
          </button>
        )}
      </div>

      <div className="flex gap-1 mb-5 border-b border-zinc-800">
        {(['posts', 'comments'] as AdminTab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition flex items-center gap-1.5 ${
              tab === t ? 'border-emerald-500 text-zinc-100' : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t === 'posts' ? (
              <>
                Posts
                {draftCount > 0 && (
                  <span className="text-[10px] bg-zinc-700 text-zinc-300 rounded-full px-1.5 py-0.5 font-mono">{draftCount}</span>
                )}
              </>
            ) : (
              <>
                Comments
                {pendingCount > 0 && (
                  <span className="text-[10px] bg-amber-900/50 text-amber-300 rounded-full px-1.5 py-0.5">{pendingCount}</span>
                )}
              </>
            )}
          </button>
        ))}
      </div>

      {tab === 'comments' ? (
        <CommentsModerationPanel onCountChange={setPendingCount} />
      ) : (
        <>
          <div className="flex gap-2 mb-5">
            {STATUS_FILTERS.map(s => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-3 py-1.5 text-xs rounded uppercase tracking-wider font-medium transition ${
                  filter === s ? 'bg-zinc-700 text-zinc-100'
                  : s === 'pending' ? 'bg-amber-950/40 text-amber-400 hover:text-amber-300'
                  : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
                }`}
              >{s === 'pending' ? 'Pending Review' : s}</button>
            ))}
          </div>

          {loading ? (
            <div className="flex items-center gap-2 text-zinc-500 text-sm"><Loader2 size={14} className="animate-spin" /> Loading…</div>
          ) : (
            <div className="space-y-6">
              {/* Drafts section */}
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Drafts</p>
                {drafts.length === 0 ? (
                  <div className="text-zinc-600 text-xs py-4 text-center border border-dashed border-zinc-800 rounded">
                    No drafts — click <span className="text-zinc-400">+ New post</span> to start one.
                  </div>
                ) : (
                  <table className="w-full text-sm border border-zinc-800 rounded overflow-hidden">
                    <thead className="bg-zinc-900 text-xs uppercase tracking-wider text-zinc-500">
                      <tr>
                        <th className="text-left px-3 py-2">Title</th>
                        <th className="text-left px-3 py-2">Slug</th>
                        <th className="text-left px-3 py-2">Status</th>
                        <th className="text-left px-3 py-2">Updated</th>
                        <th className="px-3 py-2 w-32"></th>
                      </tr>
                    </thead>
                    <tbody>{drafts.map(p => <PostRow key={p.id} p={p} />)}</tbody>
                  </table>
                )}
              </div>

              {/* Published / scheduled / archived */}
              {(filter === 'all' ? nonDrafts.length > 0 : posts.filter(p => p.status !== 'draft').length > 0) && (
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Published &amp; Archived</p>
                  <table className="w-full text-sm border border-zinc-800 rounded overflow-hidden">
                    <thead className="bg-zinc-900 text-xs uppercase tracking-wider text-zinc-500">
                      <tr>
                        <th className="text-left px-3 py-2">Title</th>
                        <th className="text-left px-3 py-2">Slug</th>
                        <th className="text-left px-3 py-2">Status</th>
                        <th className="text-left px-3 py-2">Updated</th>
                        <th className="px-3 py-2 w-32"></th>
                      </tr>
                    </thead>
                    <tbody>{nonDrafts.map(p => <PostRow key={p.id} p={p} />)}</tbody>
                  </table>
                </div>
              )}

              {posts.length === 0 && filter !== 'all' && (
                <div className="text-zinc-500 text-sm py-8 text-center border border-dashed border-zinc-800 rounded">
                  No posts with status "{filter}".
                </div>
              )}
            </div>
          )}

          {editing && (
            <BlogEditModal
              post={editing}
              onClose={() => setEditing(null)}
              onSaved={() => { setEditing(null); load() }}
            />
          )}
        </>
      )}
    </div>
  )
}

function CommentsModerationPanel({ onCountChange }: { onCountChange: (n: number) => void }) {
  const [comments, setComments] = useState<PendingComment[]>([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const rows = await api.get<PendingComment[]>('/blogs/comments/pending')
      setComments(rows)
      onCountChange(rows.length)
    } catch (e) {
      setError((e as Error).message)
      setComments([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function moderate(id: string, status: 'approved' | 'rejected') {
    setBusyId(id)
    try {
      await api.patch(`/blogs/comments/${id}?status=${status}`)
      const remaining = comments.filter(c => c.id !== id)
      setComments(remaining)
      onCountChange(remaining.length)
    } catch (e) {
      alert(`Moderation failed: ${(e as Error).message}`)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <div className="flex items-center gap-2 text-zinc-500 text-sm"><Loader2 size={14} className="animate-spin" /> Loading…</div>
  if (error) return <div className="text-amber-400 text-sm">{error}</div>
  if (comments.length === 0) {
    return (
      <div className="text-zinc-500 text-sm py-12 text-center border border-dashed border-zinc-800 rounded">
        No pending comments. New comments will appear here.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {comments.map((c) => (
        <div key={c.id} className="border border-zinc-800 rounded p-4 bg-zinc-950">
          <div className="flex items-baseline justify-between mb-2">
            <div className="text-xs text-zinc-500">
              <span className="text-zinc-300 font-medium">{c.author_name}</span>
              {c.post_title && <> on <span className="text-zinc-300">{c.post_title}</span></>}
              <span className="ml-2">{new Date(c.created_at).toLocaleString()}</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => moderate(c.id, 'approved')}
                disabled={busyId === c.id}
                className="text-emerald-400 hover:text-emerald-300 text-xs font-medium px-2.5 py-1 rounded border border-emerald-900/60 disabled:opacity-40 flex items-center gap-1"
              >
                <Check className="w-3 h-3" /> Approve
              </button>
              <button
                onClick={() => moderate(c.id, 'rejected')}
                disabled={busyId === c.id}
                className="text-amber-400 hover:text-amber-300 text-xs font-medium px-2.5 py-1 rounded border border-amber-900/60 disabled:opacity-40 flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reject
              </button>
            </div>
          </div>
          <p className="text-sm text-zinc-200 whitespace-pre-wrap">{c.content}</p>
        </div>
      ))}
    </div>
  )
}

function BlogEditModal({
  post, onClose, onSaved,
}: {
  post: BlogPost
  onClose: () => void
  onSaved: () => void
}) {
  const [title, setTitle] = useState(post.title)
  const [slug, setSlug] = useState(post.slug)
  const [content, setContent] = useState(post.content)
  const [excerpt, setExcerpt] = useState(post.excerpt ?? '')
  const [coverImage, setCoverImage] = useState(post.cover_image ?? '')
  const [status, setStatus] = useState<BlogStatus>(post.status)
  const [tagsInput, setTagsInput] = useState((post.tags ?? []).join(', '))
  const [metaTitle, setMetaTitle] = useState(post.meta_title ?? '')
  const [metaDesc, setMetaDesc] = useState(post.meta_description ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function uploadImage(file: File, target: 'cover' | 'inline') {
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await api.upload<{ url: string }>('/blogs/upload', fd)
      if (target === 'cover') setCoverImage(res.url)
      else setContent(c => `${c}\n\n![${file.name}](${res.url})\n`)
    } catch (err) {
      alert(`Upload failed: ${(err as Error).message}`)
    }
  }

  async function save() {
    setError(null)
    if (!title.trim()) { setError('Title required'); return }
    if (!slug.trim()) { setError('Slug required'); return }
    if (!content.trim()) { setError('Content required'); return }

    const tags = tagsInput.split(',').map(t => t.trim()).filter(Boolean)
    const body = {
      title, slug, content,
      excerpt: excerpt || null,
      cover_image: coverImage || null,
      status,
      tags,
      meta_title: metaTitle || null,
      meta_description: metaDesc || null,
    }

    setSaving(true)
    try {
      await api.put(`/blogs/${post.id}`, body)
      onSaved()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6" onClick={onClose}>
      <div
        className="bg-zinc-950 border border-zinc-800 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-100">Edit post</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-sm">Close</button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Title</label>
            <input type="text" value={title} onChange={e => setTitle(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              placeholder="My great post" />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Slug (/blog/&lt;slug&gt;)</label>
            <input type="text" value={slug} onChange={e => setSlug(slugify(e.target.value))}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono mt-1"
              placeholder="my-great-post" />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Excerpt (optional, ~160 chars)</label>
            <textarea value={excerpt} onChange={e => setExcerpt(e.target.value)} rows={2}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1 resize-none"
              placeholder="One-line summary shown on blog index" />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Cover image</label>
            <div className="flex items-center gap-2 mt-1">
              <input type="text" value={coverImage} onChange={e => setCoverImage(e.target.value)}
                className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono"
                placeholder="https://..." />
              <label className="bg-zinc-800 hover:bg-zinc-700 px-3 py-2 text-xs text-zinc-300 rounded cursor-pointer">
                Upload
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadImage(f, 'cover') }} />
              </label>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Content (markdown)</label>
              <label className="text-[10px] text-zinc-400 hover:text-zinc-200 cursor-pointer">
                Insert image
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadImage(f, 'inline') }} />
              </label>
            </div>
            <textarea value={content} onChange={e => setContent(e.target.value)} rows={16}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono mt-1"
              placeholder={'# Heading\n\nParagraph text...'} />
            <div className="text-[10px] text-zinc-600 mt-1">
              Paste markdown from a Matcha Work blog project's "Markdown" export.
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Tags (comma-separated)</label>
              <input type="text" value={tagsInput} onChange={e => setTagsInput(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
                placeholder="hr, compliance" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Status</label>
              <select value={status} onChange={e => setStatus(e.target.value as BlogStatus)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1">
                <option value="draft">Draft</option>
                <option value="published">Published</option>
                <option value="archived">Archived</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta title (SEO)</label>
              <input type="text" value={metaTitle} onChange={e => setMetaTitle(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta description (SEO)</label>
              <input type="text" value={metaDesc} onChange={e => setMetaDesc(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1" />
            </div>
          </div>

          {error && <div className="text-red-400 text-xs">{error}</div>}
        </div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800">
          <button onClick={onClose} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={save} disabled={saving}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
