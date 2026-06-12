import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Newspaper, Pencil } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell from '../../../components/cappe/SurfaceShell'
import type { CappePost } from '../../../types/cappe'

const EMPTY = { title: '', excerpt: '', body: '', cover_image_url: '', status: 'draft' as const }

const statusStyle: Record<string, string> = {
  draft: 'bg-zinc-100 text-zinc-600',
  published: 'bg-emerald-100 text-emerald-700',
  archived: 'bg-amber-100 text-amber-700',
}

export default function Blog() {
  const { siteId } = useParams<{ siteId: string }>()
  const [posts, setPosts] = useState<CappePost[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState<{ title: string; excerpt: string; body: string; cover_image_url: string; status: string }>(EMPTY)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    cappeApi
      .get<CappePost[]>(`/sites/${siteId}/posts`)
      .then(setPosts)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load posts'))
  }, [siteId])

  function startNew() { setEditId(null); setForm(EMPTY); setEditing(true) }
  function startEdit(p: CappePost) {
    setEditId(p.id)
    setForm({ title: p.title, excerpt: p.excerpt || '', body: p.body || '', cover_image_url: p.cover_image_url || '', status: p.status })
    setEditing(true)
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!form.title.trim()) return
    setSaving(true)
    setError(null)
    const payload = {
      title: form.title.trim(),
      excerpt: form.excerpt.trim() || null,
      body: form.body,
      cover_image_url: form.cover_image_url.trim() || null,
      status: form.status,
    }
    try {
      if (editId) {
        const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${editId}`, payload)
        setPosts((p) => (p || []).map((x) => (x.id === editId ? updated : x)))
      } else {
        const created = await cappeApi.post<CappePost>(`/sites/${siteId}/posts`, payload)
        setPosts((p) => [created, ...(p || [])])
      }
      setEditing(false)
      setForm(EMPTY)
      setEditId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save post')
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: string) {
    await cappeApi.delete(`/sites/${siteId}/posts/${id}`)
    setPosts((p) => (p || []).filter((x) => x.id !== id))
  }

  return (
    <SurfaceShell
      title="Blog"
      subtitle="Write and publish posts."
      actions={
        <button onClick={startNew} className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700">
          <Plus className="h-4 w-4" /> New post
        </button>
      }
    >
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {editing && (
        <form onSubmit={save} className="mb-6 space-y-3 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Post title" className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
          <input value={form.excerpt} onChange={(e) => setForm({ ...form, excerpt: e.target.value })} placeholder="Excerpt (optional)" className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
          <input value={form.cover_image_url} onChange={(e) => setForm({ ...form, cover_image_url: e.target.value })} placeholder="Cover image URL (optional)" className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
          <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} placeholder="Write your post (Markdown)…" rows={10} className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
          <div className="flex items-center gap-3">
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="rounded-lg border border-zinc-300 px-2 py-2 text-sm">
              <option value="draft">Draft</option>
              <option value="published">Published</option>
              <option value="archived">Archived</option>
            </select>
            <button type="submit" disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} {editId ? 'Save' : 'Create'}
            </button>
            <button type="button" onClick={() => { setEditing(false); setForm(EMPTY); setEditId(null) }} className="text-sm text-zinc-500 hover:text-zinc-800">Cancel</button>
          </div>
        </form>
      )}

      {posts === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : posts.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-12 text-center text-sm text-zinc-500">
          <Newspaper className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No posts yet.
        </div>
      ) : (
        <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white">
          {posts.map((p) => (
            <div key={p.id} className="flex items-center gap-4 px-5 py-3">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-zinc-900">{p.title}</div>
                <div className="text-xs text-zinc-400">/{p.slug}</div>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[p.status]}`}>{p.status}</span>
              <button onClick={() => startEdit(p)} className="text-zinc-400 hover:text-emerald-700"><Pencil className="h-4 w-4" /></button>
              <button onClick={() => remove(p.id)} className="text-zinc-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
