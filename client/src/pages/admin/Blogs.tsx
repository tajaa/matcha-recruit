import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../../api/client'
import { Plus } from 'lucide-react'
import type { AdminTab, PendingComment } from './Blogs/types'
import { usePosts } from './Blogs/usePosts'
import BlogComposer from './Blogs/BlogComposer'
import PostsList from './Blogs/PostsList'
import CommentsModerationPanel from './Blogs/CommentsModerationPanel'

export default function Blogs() {
  const navigate = useNavigate()
  const location = useLocation()

  const initialTab: AdminTab =
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('tab') === 'comments'
      ? 'comments'
      : 'posts'
  const [tab, setTab] = useState<AdminTab>(initialTab)
  const [pendingCount, setPendingCount] = useState<number>(0)

  const { posts, setPosts, loading, filter, setFilter, editing, setEditing, load, approve, reject, deletePost } = usePosts()

  const isComposer = location.pathname.endsWith('/composer')

  useEffect(() => {
    api.get<PendingComment[]>('/blogs/comments/pending')
      .then(rows => setPendingCount(rows.length))
      .catch(() => setPendingCount(0))
  }, [])

  const draftCount = posts.filter(p => p.status === 'draft').length

  // ── Composer view ────────────────────────────────────────────────────────
  if (isComposer) {
    return <BlogComposer isComposer={isComposer} setPosts={setPosts} load={load} />
  }

  // ── Posts list view ──────────────────────────────────────────────────────
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
        <PostsList
          posts={posts}
          loading={loading}
          filter={filter}
          setFilter={setFilter}
          editing={editing}
          setEditing={setEditing}
          load={load}
          approve={approve}
          reject={reject}
          deletePost={deletePost}
        />
      )}
    </div>
  )
}
