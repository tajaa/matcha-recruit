import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../../../api/client'
import { slugify } from './slugify'
import type { BlogPost, BlogStatus } from './types'

export function useComposer({
  isComposer, setPosts, load,
}: {
  isComposer: boolean
  setPosts: Dispatch<SetStateAction<BlogPost[]>>
  load: () => void | Promise<void>
}) {
  const navigate = useNavigate()
  const location = useLocation()

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

  return {
    navigate,
    composeTitle, setComposeTitle,
    composeSlug, setComposeSlug,
    composeContent, setComposeContent,
    composeExcerpt, setComposeExcerpt,
    composeCover, setComposeCover,
    composeTags, setComposeTags,
    composeMetaTitle, setComposeMetaTitle,
    composeMetaDesc, setComposeMetaDesc,
    autoSlug, setAutoSlug,
    isDirty, saveStatus, composeId, composeSaving,
    publishCompose, uploadCover, mark,
  }
}
