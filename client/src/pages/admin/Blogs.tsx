import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Pencil, Plus, Trash2, ExternalLink } from 'lucide-react'

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
}

type BlogList = { items: BlogPost[]; total: number }

const STATUS_FILTERS: Array<BlogStatus | 'all'> = ['all', 'draft', 'published', 'archived']

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 80)
}

export default function Blogs() {
  const [posts, setPosts] = useState<BlogPost[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<BlogStatus | 'all'>('all')
  const [editing, setEditing] = useState<BlogPost | null>(null)
  const [creating, setCreating] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: '1', limit: '100' })
      if (filter !== 'all') params.set('status', filter)
      const data = await api.get<BlogList>(`/blogs?${params}`)
      setPosts(data.items)
    } catch (err) {
      console.error('Load blogs failed', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filter])

  async function deletePost(id: string) {
    if (!confirm('Delete this post permanently?')) return
    try {
      await api.delete(`/blogs/${id}`)
      await load()
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`)
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Blog</h1>
          <p className="text-xs text-zinc-500 mt-1">Posts publish to the public landing page at /blog.</p>
        </div>
        <button
          onClick={() => { setCreating(true); setEditing(null) }}
          className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-2 rounded text-sm font-medium flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> New post
        </button>
      </div>

      <div className="flex gap-2 mb-4">
        {STATUS_FILTERS.map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 text-xs rounded uppercase tracking-wider font-medium transition ${
              filter === s ? 'bg-zinc-700 text-zinc-100' : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
            }`}
          >{s}</button>
        ))}
      </div>

      {loading ? (
        <div className="text-zinc-500 text-sm">Loading…</div>
      ) : posts.length === 0 ? (
        <div className="text-zinc-500 text-sm py-12 text-center border border-dashed border-zinc-800 rounded">
          No posts. Click "New post" to draft one.
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
          <tbody>
            {posts.map(p => (
              <tr key={p.id} className="border-t border-zinc-800 hover:bg-zinc-900/40">
                <td className="px-3 py-2 text-zinc-100">{p.title}</td>
                <td className="px-3 py-2 text-zinc-500 font-mono text-xs">{p.slug}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] px-2 py-0.5 rounded uppercase tracking-wider font-mono ${
                    p.status === 'published'
                      ? 'bg-emerald-900/40 text-emerald-400'
                      : p.status === 'draft'
                      ? 'bg-zinc-800 text-zinc-400'
                      : 'bg-zinc-900 text-zinc-600'
                  }`}>{p.status}</span>
                </td>
                <td className="px-3 py-2 text-zinc-500 text-xs">{new Date(p.updated_at).toLocaleDateString()}</td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-2">
                    {p.status === 'published' && (
                      <a
                        href={`/blog/${p.slug}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-zinc-500 hover:text-zinc-300"
                        title="View on site"
                      ><ExternalLink className="w-4 h-4" /></a>
                    )}
                    <button onClick={() => { setEditing(p); setCreating(false) }} className="text-zinc-500 hover:text-zinc-300" title="Edit">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deletePost(p.id)} className="text-zinc-500 hover:text-red-400" title="Delete">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(creating || editing) && (
        <BlogEditModal
          post={editing}
          onClose={() => { setCreating(false); setEditing(null) }}
          onSaved={() => { setCreating(false); setEditing(null); load() }}
        />
      )}
    </div>
  )
}

function BlogEditModal({
  post, onClose, onSaved,
}: {
  post: BlogPost | null
  onClose: () => void
  onSaved: () => void
}) {
  const isNew = post === null
  const [title, setTitle] = useState(post?.title ?? '')
  const [slug, setSlug] = useState(post?.slug ?? '')
  const [content, setContent] = useState(post?.content ?? '')
  const [excerpt, setExcerpt] = useState(post?.excerpt ?? '')
  const [coverImage, setCoverImage] = useState(post?.cover_image ?? '')
  const [status, setStatus] = useState<BlogStatus>(post?.status ?? 'draft')
  const [tagsInput, setTagsInput] = useState((post?.tags ?? []).join(', '))
  const [metaTitle, setMetaTitle] = useState(post?.meta_title ?? '')
  const [metaDesc, setMetaDesc] = useState(post?.meta_description ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoSlug, setAutoSlug] = useState(isNew)

  useEffect(() => {
    if (autoSlug) setSlug(slugify(title))
  }, [title, autoSlug])

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
      if (isNew) {
        await api.post('/blogs', body)
      } else if (post) {
        await api.put(`/blogs/${post.id}`, body)
      }
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
          <h2 className="text-sm font-semibold text-zinc-100">{isNew ? 'New post' : 'Edit post'}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-sm">Close</button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Title</label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              placeholder="My great post"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 flex items-center justify-between">
              <span>Slug (URL: /blog/&lt;slug&gt;)</span>
              {isNew && (
                <label className="flex items-center gap-1 normal-case text-zinc-400">
                  <input
                    type="checkbox"
                    checked={autoSlug}
                    onChange={e => setAutoSlug(e.target.checked)}
                  />
                  <span>Auto from title</span>
                </label>
              )}
            </label>
            <input
              type="text"
              value={slug}
              onChange={e => { setSlug(slugify(e.target.value)); setAutoSlug(false) }}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono mt-1"
              placeholder="my-great-post"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Excerpt (optional, ~160 chars)</label>
            <textarea
              value={excerpt ?? ''}
              onChange={e => setExcerpt(e.target.value)}
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
                value={coverImage ?? ''}
                onChange={e => setCoverImage(e.target.value)}
                className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono"
                placeholder="https://..."
              />
              <label className="bg-zinc-800 hover:bg-zinc-700 px-3 py-2 text-xs text-zinc-300 rounded cursor-pointer">
                Upload
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadImage(f, 'cover') }}
                />
              </label>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Content (markdown)</label>
              <label className="text-[10px] text-zinc-400 hover:text-zinc-200 cursor-pointer">
                Insert image
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadImage(f, 'inline') }}
                />
              </label>
            </div>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              rows={16}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono mt-1"
              placeholder="# Heading\n\nParagraph text...\n\n![alt](image-url)"
            />
            <div className="text-[10px] text-zinc-600 mt-1">
              Paste markdown from a Matcha Work blog project's "Markdown" export.
              Supports headings, lists, links, images, and `&lt;video src=&quot;...&quot;&gt;` tags.
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Tags (comma-separated)</label>
              <input
                type="text"
                value={tagsInput}
                onChange={e => setTagsInput(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
                placeholder="hr, compliance"
              />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Status</label>
              <select
                value={status}
                onChange={e => setStatus(e.target.value as BlogStatus)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              >
                <option value="draft">Draft</option>
                <option value="published">Published</option>
                <option value="archived">Archived</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta title (SEO)</label>
              <input
                type="text"
                value={metaTitle ?? ''}
                onChange={e => setMetaTitle(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta description (SEO)</label>
              <input
                type="text"
                value={metaDesc ?? ''}
                onChange={e => setMetaDesc(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              />
            </div>
          </div>

          {error && <div className="text-red-400 text-xs">{error}</div>}
        </div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          >Cancel</button>
          <button
            onClick={save}
            disabled={saving}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium"
          >{saving ? 'Saving…' : isNew ? 'Create' : 'Save'}</button>
        </div>
      </div>
    </div>
  )
}
