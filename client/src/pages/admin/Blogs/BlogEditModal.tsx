import { useState } from 'react'
import { api } from '../../../api/client'
import { slugify } from './slugify'
import type { BlogPost, BlogStatus } from './types'

export default function BlogEditModal({
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
