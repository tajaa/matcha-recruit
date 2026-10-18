import { AdminButton } from '../../../../components/admin/AdminUI'
import { AdminTab, AdminTabBar } from '../../../../components/admin/AdminTabs'
import { AdminPageHeader } from '../../../../components/admin/AdminPageHeader'
import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../../../../api/client'
import { Plus } from 'lucide-react'
import type { AdminTab as BlogAdminTab, PendingComment } from './types'
import { usePosts } from './usePosts'
import BlogComposer from './BlogComposer'
import PostsList from './PostsList'
import CommentsModerationPanel from './CommentsModerationPanel'

export default function Blogs() {
  const navigate = useNavigate()
  const location = useLocation()

  const initialTab: BlogAdminTab =
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('tab') === 'comments'
      ? 'comments'
      : 'posts'
  const [tab, setTab] = useState<BlogAdminTab>(initialTab)
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
    <div>
      <AdminPageHeader
        title="Blog"
        description="Posts publish to the public landing page at /blog."
        actions={tab === 'posts' ? (
          <AdminButton
            onClick={() => navigate('/admin/blogs/composer')}
            className="gap-2" variant="success"
          >
            <Plus className="w-4 h-4" /> New post
          </AdminButton>
        ) : null}
      />

      <AdminTabBar className="mb-5">
        {(['posts', 'comments'] as BlogAdminTab[]).map(t => (
          <AdminTab
            key={t}
            onClick={() => setTab(t)}
           active={tab === t}
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
          </AdminTab>
        ))}
      </AdminTabBar>

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
