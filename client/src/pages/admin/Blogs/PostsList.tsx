import { type Dispatch, type SetStateAction } from 'react'
import { Pencil, Trash2, ExternalLink, Loader2 } from 'lucide-react'
import { STATUS_FILTERS } from './constants'
import BlogEditModal from './BlogEditModal'
import type { BlogPost, BlogStatus } from './types'

export default function PostsList({
  posts, loading, filter, setFilter, editing, setEditing, load, approve, reject, deletePost,
}: {
  posts: BlogPost[]
  loading: boolean
  filter: BlogStatus | 'all' | 'pending'
  setFilter: (f: BlogStatus | 'all' | 'pending') => void
  editing: BlogPost | null
  setEditing: Dispatch<SetStateAction<BlogPost | null>>
  load: () => void | Promise<void>
  approve: (p: BlogPost) => void | Promise<void>
  reject: (p: BlogPost) => void | Promise<void>
  deletePost: (id: string) => void | Promise<void>
}) {
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
  )
}
