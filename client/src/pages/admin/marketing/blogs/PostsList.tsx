import { AdminButton, AdminTable } from '../../../../components/admin/AdminUI'
import { AdminTab, AdminTabBar } from '../../../../components/admin/AdminTabs'
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
      <td className="text-zinc-100">{p.title}</td>
      <td className="text-zinc-500 font-mono">{p.slug}</td>
      <td >
        <div className="flex items-center gap-1.5">
          <span className={`text-[10px] px-2 py-0.5 rounded capitalize font-mono ${
            p.status === 'published' ? 'bg-emerald-900/40 text-emerald-400'
            : p.status === 'draft' ? 'bg-zinc-800 text-zinc-400'
            : 'bg-zinc-900 text-zinc-600'
          }`}>{p.status}</span>
          {p.submitted_for_review && (
            <span className="text-[10px] px-2 py-0.5 rounded capitalize font-mono bg-amber-900/40 text-amber-400">review</span>
          )}
        </div>
      </td>
      <td className="text-zinc-500">{new Date(p.updated_at).toLocaleDateString()}</td>
      <td className="text-right">
        <div className="flex justify-end gap-2">
          {p.submitted_for_review && (
            <>
              <AdminButton onClick={() => approve(p)}  variant="success">Approve</AdminButton>
              <AdminButton onClick={() => reject(p)} className="text-amber-400! hover:text-amber-300!" variant="ghost">Reject</AdminButton>
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
      <AdminTabBar className="mb-5!" role="group" aria-label="Status">
        {STATUS_FILTERS.map(s => (
          <AdminTab
            key={s}
            active={filter === s}
            onClick={() => setFilter(s)}
            className={`capitalize ${filter !== s && s === 'pending' ? 'text-amber-400! hover:text-amber-300!' : ''}`}
          >{s === 'pending' ? 'Pending review' : s}</AdminTab>
        ))}
      </AdminTabBar>

      {loading ? (
        <div className="flex items-center gap-2 text-zinc-500 text-sm"><Loader2 size={14} className="animate-spin" /> Loading…</div>
      ) : (
        <div className="space-y-6">
          {/* Drafts section */}
          <div>
            <p className="text-[11px] text-zinc-500 mb-2">Drafts</p>
            {drafts.length === 0 ? (
              <div className="text-zinc-600 text-xs py-4 text-center border border-dashed border-zinc-800 rounded">
                No drafts — click <span className="text-zinc-400">+ New post</span> to start one.
              </div>
            ) : (
              <AdminTable className="border border-zinc-800 rounded overflow-hidden">
                <thead >
                  <tr>
                    <th className="text-left">Title</th>
                    <th className="text-left">Slug</th>
                    <th className="text-left">Status</th>
                    <th className="text-left">Updated</th>
                    <th className="w-32"></th>
                  </tr>
                </thead>
                <tbody>{drafts.map(p => <PostRow key={p.id} p={p} />)}</tbody>
              </AdminTable>
            )}
          </div>

          {/* Published / scheduled / archived */}
          {(filter === 'all' ? nonDrafts.length > 0 : posts.filter(p => p.status !== 'draft').length > 0) && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-2">Published &amp; Archived</p>
              <AdminTable className="border border-zinc-800 rounded overflow-hidden">
                <thead >
                  <tr>
                    <th className="text-left">Title</th>
                    <th className="text-left">Slug</th>
                    <th className="text-left">Status</th>
                    <th className="text-left">Updated</th>
                    <th className="w-32"></th>
                  </tr>
                </thead>
                <tbody>{nonDrafts.map(p => <PostRow key={p.id} p={p} />)}</tbody>
              </AdminTable>
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
