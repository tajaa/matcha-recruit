import { useEffect, useState } from 'react'
import { api } from '../../../api/client'
import type { BlogList, BlogPost, BlogStatus } from './types'

export function usePosts() {
  const [posts, setPosts] = useState<BlogPost[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<BlogStatus | 'all' | 'pending'>('all')
  const [editing, setEditing] = useState<BlogPost | null>(null)

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

  return { posts, setPosts, loading, filter, setFilter, editing, setEditing, load, approve, reject, deletePost }
}
