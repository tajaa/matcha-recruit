import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../../api/client'
import type { Subscriber, Newsletter, SubStats, Tag, Template, Idea, GrowthPoint, Analytics, Progress, Tab } from './types'
import { type ComposeMode } from './ComposeTab'
import { emptyDesign, type NewsletterDesign } from './blocks/schema'
import type { ViewportKey } from './MobilePreview'

export function useNewsletterAdmin() {
  const location = useLocation()
  const [tab, setTab] = useState<Tab>('subscribers')
  const [subscribers, setSubs] = useState<Subscriber[]>([])
  const [stats, setStats] = useState<SubStats | null>(null)
  const [newsletters, setNewsletters] = useState<Newsletter[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [ideas, setIdeas] = useState<Idea[]>([])
  const [growth, setGrowth] = useState<GrowthPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  // Compose state
  const [composeTitle, setComposeTitle] = useState('')
  const [composeSubject, setComposeSubject] = useState('')
  const [composePreheader, setComposePreheader] = useState('')
  const [composeHtml, setComposeHtml] = useState('')
  const [composeMode, setComposeMode] = useState<ComposeMode>('design')
  const [composeDesign, setComposeDesign] = useState<NewsletterDesign | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  const [previewViewport, setPreviewViewport] = useState<ViewportKey>('mobile')

  // Send modal state
  const [sendModal, setSendModal] = useState<{ kind: 'now' | 'schedule' | 'segment' } | null>(null)
  const [sendSegmentTags, setSendSegmentTags] = useState<string[]>([])
  const [sendScheduledAt, setSendScheduledAt] = useState('')
  const [sending, setSending] = useState(false)

  // Live progress for the in-flight newsletter (polled while sending).
  const [progress, setProgress] = useState<Progress | null>(null)
  const progressTargetRef = useRef<string | null>(null)
  // Stop signal for the polling loop. Setting `.current = true` halts the
  // active loop on its next tick. A new loop resets it.
  const progressStopRef = useRef(false)

  // Per-newsletter analytics drawer
  const [analyticsOpen, setAnalyticsOpen] = useState<string | null>(null)
  const [analytics, setAnalytics] = useState<Analytics | null>(null)

  // CSV import
  const [importOpen, setImportOpen] = useState(false)

  // Group (tag) management per subscriber
  const [managingTagsFor, setManagingTagsFor] = useState<string | null>(null)
  const [subTagsCache, setSubTagsCache] = useState<Record<string, Tag[]>>({})

  useEffect(() => { loadData() }, [])

  // Sync tab with route: /admin/newsletter/composer → compose tab
  useEffect(() => {
    if (location.pathname.endsWith('/composer')) {
      setTab('compose')
      setEditingId(null)
      setComposeTitle(''); setComposeSubject(''); setComposePreheader(''); setComposeHtml('')
      setComposeDesign(emptyDesign('light')); setComposeMode('design')
      setIsDirty(false); setSaveStatus('saved')
    }
  }, [location.pathname])

  async function loadData() {
    setLoading(true)
    try {
      const [subRes, nlRes, tagsRes, tplRes, ideasRes, growthRes] = await Promise.allSettled([
        api.get<{ subscribers: Subscriber[]; total: number; stats: SubStats }>('/admin/newsletter/subscribers?limit=100'),
        api.get<Newsletter[]>('/admin/newsletter/newsletters'),
        api.get<{ tags: Tag[] }>('/admin/newsletter/tags'),
        api.get<{ templates: Template[] }>('/admin/newsletter/templates'),
        api.get<{ ideas: Idea[] }>('/admin/newsletter/ideas'),
        api.get<{ days: number; series: GrowthPoint[] }>('/admin/newsletter/subscribers/growth?days=90'),
      ])
      if (subRes.status === 'fulfilled') {
        setSubs(subRes.value.subscribers)
        setStats(subRes.value.stats)
      }
      if (nlRes.status === 'fulfilled') setNewsletters(nlRes.value)
      if (tagsRes.status === 'fulfilled') setTags(tagsRes.value.tags)
      if (tplRes.status === 'fulfilled') setTemplates(tplRes.value.templates)
      if (ideasRes.status === 'fulfilled') setIdeas(ideasRes.value.ideas)
      if (growthRes.status === 'fulfilled') setGrowth(growthRes.value.series)
    } catch {}
    setLoading(false)
  }

  // Poll send progress every 3s while a newsletter is in 'sending' state.
  // The polling loop is keyed on a unique target id (the newsletter being
  // sent). The previous version re-fired on every status change and could
  // briefly run two parallel `tick()` loops; this one uses a single ref
  // flag so only one loop is ever active.
  useEffect(() => {
    const target = progressTargetRef.current
    if (!target || progress?.newsletter_status !== 'sending') return
    progressStopRef.current = false
    async function tick() {
      while (!progressStopRef.current) {
        try {
          const p = await api.get<Progress>(`/admin/newsletter/newsletters/${target}/progress`)
          setProgress(p)
          if (p.newsletter_status !== 'sending') {
            progressStopRef.current = true
            loadData()
            return
          }
        } catch {}
        await new Promise((r) => setTimeout(r, 3000))
      }
    }
    tick()
    return () => { progressStopRef.current = true }
  }, [progress?.newsletter_status])

  // Body of the save payload, shaped by the active editor mode. Design mode
  // sends design_json (server renders the content_html snapshot); HTML mode
  // sends content_html and nulls design_json so the two can't fight.
  function savePayload() {
    const base = {
      title: composeTitle.trim() || undefined,
      subject: composeSubject.trim() || undefined,
      preheader: composePreheader || undefined,
    }
    if (composeMode === 'design') {
      return { ...base, design_json: composeDesign ?? emptyDesign('light') }
    }
    return { ...base, content_html: composeHtml || undefined, design_json: null }
  }

  // Auto-save: 2s after last keystroke, create or update draft
  useEffect(() => {
    if (!isDirty) return
    const canCreate = composeTitle.trim() && composeSubject.trim()
    if (!editingId && !canCreate) return
    setSaveStatus('saving')
    const timer = window.setTimeout(async () => {
      try {
        let id = editingId
        if (!id) {
          const created = await api.post<Newsletter>('/admin/newsletter/newsletters', {
            title: composeTitle.trim(), subject: composeSubject.trim(),
          })
          id = created.id
          setEditingId(created.id)
          upsertNewsletter(created)
        }
        const saved = await api.put<Newsletter>(`/admin/newsletter/newsletters/${id}`, savePayload())
        upsertNewsletter(saved)
        setIsDirty(false)
        setSaveStatus('saved')
      } catch {
        setSaveStatus('unsaved')
      }
    }, 2000)
    return () => window.clearTimeout(timer)
  }, [composeTitle, composeSubject, composePreheader, composeHtml, composeMode, composeDesign, isDirty])

  useEffect(() => {
    function handler(e: BeforeUnloadEvent) {
      if (isDirty) { e.preventDefault(); e.returnValue = '' }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  // Merge a freshly-saved row back into the list. startEdit() reopens a draft
  // from `newsletters` state, so without this the list keeps the POST-create
  // row (content_html=null) and reopening shows a blank body. Spread-merge so
  // list-only aggregates (total_sends/total_opened) survive.
  function upsertNewsletter(saved: Newsletter) {
    setNewsletters((prev) =>
      prev.some(n => n.id === saved.id)
        ? prev.map(n => (n.id === saved.id ? { ...n, ...saved } : n))
        : [saved, ...prev]
    )
  }

  async function handleCreate() {
    if (!composeTitle.trim() || !composeSubject.trim()) return
    setSaving(true)
    try {
      const nl = await api.post<Newsletter>('/admin/newsletter/newsletters', {
        title: composeTitle.trim(), subject: composeSubject.trim(),
      })
      setEditingId(nl.id)
      setNewsletters((prev) => prev.some(n => n.id === nl.id) ? prev : [nl, ...prev])
      setIsDirty(false); setSaveStatus('saved')
    } catch {}
    setSaving(false)
  }

  async function handleSave() {
    if (!editingId) return
    setSaving(true)
    try {
      const saved = await api.put<Newsletter>(`/admin/newsletter/newsletters/${editingId}`, savePayload())
      upsertNewsletter(saved)
      setIsDirty(false); setSaveStatus('saved')
    } catch {}
    setSaving(false)
  }

  async function openSend(kind: 'now' | 'schedule' | 'segment') {
    if (!editingId) return
    await handleSave()
    setSendSegmentTags([])
    setSendScheduledAt('')
    setSendModal({ kind })
  }

  async function confirmSend() {
    if (!editingId || !sendModal) return
    setSending(true)
    try {
      if (sendModal.kind === 'schedule') {
        if (!sendScheduledAt) {
          alert('Pick a date/time first.')
          setSending(false)
          return
        }
        await api.post(`/admin/newsletter/newsletters/${editingId}/schedule`, {
          scheduled_at: new Date(sendScheduledAt).toISOString(),
        })
        alert(`Scheduled for ${new Date(sendScheduledAt).toLocaleString()}.`)
      } else if (sendModal.kind === 'segment') {
        const result = await api.post<{ queued: number }>(
          `/admin/newsletter/newsletters/${editingId}/send-segment`,
          { tag_slugs: sendSegmentTags.length ? sendSegmentTags : null },
        )
        progressTargetRef.current = editingId
        setProgress({ newsletter_status: 'sending', queued: result.queued, sent: 0, failed: 0, pending: result.queued, opened: 0, clicked: 0, bounced: 0 })
      } else {
        const result = await api.post<{ queued: number }>(
          `/admin/newsletter/newsletters/${editingId}/send`,
        )
        progressTargetRef.current = editingId
        setProgress({ newsletter_status: 'sending', queued: result.queued, sent: 0, failed: 0, pending: result.queued, opened: 0, clicked: 0, bounced: 0 })
      }
      setSendModal(null)
      setEditingId(null)
      setComposeTitle(''); setComposeSubject(''); setComposePreheader(''); setComposeHtml('')
      setComposeDesign(emptyDesign('light')); setComposeMode('design')
      setIsDirty(false); setSaveStatus('saved')
      setTab('newsletters')
      loadData()
    } catch (err) {
      alert(`Send failed: ${(err as Error).message}`)
    }
    setSending(false)
  }

  async function handleTestSend() {
    if (!editingId) return
    const to = prompt('Send test to which email?', '')
    if (!to || !to.includes('@')) return
    try {
      await handleSave()
      await api.post(`/admin/newsletter/newsletters/${editingId}/test-send`, { to_email: to.trim() })
      alert(`Test sent to ${to}.`)
    } catch (err) {
      alert(`Test send failed: ${(err as Error).message}`)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Soft-delete this draft?')) return
    try {
      await api.delete(`/admin/newsletter/newsletters/${id}`)
      setNewsletters((prev) => prev.filter((n) => n.id !== id))
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`)
    }
  }

  async function handleDeleteSubscriber(id: string, email: string) {
    if (!confirm(`Permanently delete ${email}? GDPR — cannot be undone.`)) return
    try {
      await api.delete(`/admin/newsletter/subscribers/${id}`)
      setSubs((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`)
    }
  }

  async function handleExport() {
    try {
      const res = await api.get<{ subscribers: Subscriber[] }>('/admin/newsletter/subscribers?limit=1000&export=true')
      const csv = [
        'email,name,source,status,subscribed_at',
        ...res.subscribers.map((s) => `${s.email},"${(s.name || '').replace(/"/g, '""')}",${s.source},${s.status},${s.subscribed_at}`),
      ].join('\n')
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `newsletter-subscribers-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert(`Export failed: ${(err as Error).message}`)
    }
  }

  function startEdit(nl: Newsletter) {
    setEditingId(nl.id)
    setComposeTitle(nl.title)
    setComposeSubject(nl.subject)
    setComposePreheader(nl.preheader ?? '')
    setComposeHtml(nl.content_html || '')
    if (nl.design_json) {
      setComposeDesign(nl.design_json)
      setComposeMode('design')
    } else {
      setComposeDesign(emptyDesign('light'))
      setComposeMode(nl.content_html ? 'html' : 'design')
    }
    setIsDirty(false)
    setSaveStatus('saved')
    setTab('compose')
  }

  function startFromDesign(design: NewsletterDesign, name: string) {
    setComposeTitle(name)
    setComposeSubject(name)
    setComposePreheader('')
    setComposeHtml('')
    setComposeDesign(design)
    setComposeMode('design')
    setEditingId(null)
    setIsDirty(true); setSaveStatus('unsaved')
    setTab('compose')
  }

  async function fromTemplate(t: Template) {
    setComposeTitle(t.name)
    setComposeSubject(t.name)
    setComposePreheader(t.preheader ?? '')
    setComposeHtml(t.content_html ?? '')
    if (t.design_json) {
      setComposeDesign(t.design_json)
      setComposeMode('design')
    } else {
      setComposeDesign(emptyDesign('light'))
      setComposeMode(t.content_html ? 'html' : 'design')
    }
    setEditingId(null)
    setIsDirty(true); setSaveStatus('unsaved')
    setTab('compose')
  }

  async function openAnalytics(nl: Newsletter) {
    setAnalyticsOpen(nl.id)
    setAnalytics(null)
    try {
      const a = await api.get<Analytics>(`/admin/newsletter/newsletters/${nl.id}/analytics`)
      setAnalytics(a)
    } catch {}
  }

  async function loadSubTags(subscriberId: string) {
    if (subTagsCache[subscriberId] !== undefined) return
    try {
      const res = await api.get<{ tags: Tag[] }>(`/admin/newsletter/subscribers/${subscriberId}/tags`)
      setSubTagsCache(prev => ({ ...prev, [subscriberId]: res.tags }))
    } catch {}
  }

  async function toggleSubTag(subscriberId: string, tagId: string) {
    const current = subTagsCache[subscriberId] ?? []
    const has = current.some(t => t.id === tagId)
    const found = tags.find(t => t.id === tagId)
    const next = has ? current.filter(t => t.id !== tagId) : found ? [...current, found] : current
    try {
      await api.put(`/admin/newsletter/subscribers/${subscriberId}/tags`, { tag_ids: next.map(t => t.id) })
      setSubTagsCache(prev => ({ ...prev, [subscriberId]: next }))
      const tagRes = await api.get<{ tags: Tag[] }>('/admin/newsletter/tags')
      setTags(tagRes.tags)
    } catch {}
  }

  const filteredSubs = useMemo(() => subscribers.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.email.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q)
  }), [subscribers, search])

  function handleTabChange(next: Tab) {
    if (tab === 'compose' && isDirty) {
      if (!confirm('You have unsaved changes. Leave compose?')) return
    }
    setTab(next)
  }

  return {
    tab, setTab,
    subscribers,
    stats,
    newsletters,
    tags, setTags,
    templates,
    ideas,
    growth,
    loading,
    search, setSearch,
    composeTitle, setComposeTitle,
    composeSubject, setComposeSubject,
    composePreheader, setComposePreheader,
    composeHtml, setComposeHtml,
    composeMode, setComposeMode,
    composeDesign, setComposeDesign,
    editingId,
    saving,
    isDirty, setIsDirty,
    saveStatus, setSaveStatus,
    previewViewport, setPreviewViewport,
    sendModal, setSendModal,
    sendSegmentTags, setSendSegmentTags,
    sendScheduledAt, setSendScheduledAt,
    sending,
    progress,
    analyticsOpen, setAnalyticsOpen,
    analytics,
    importOpen, setImportOpen,
    managingTagsFor, setManagingTagsFor,
    subTagsCache,
    filteredSubs,
    loadData,
    upsertNewsletter,
    handleCreate,
    handleSave,
    openSend,
    confirmSend,
    handleTestSend,
    handleDelete,
    handleDeleteSubscriber,
    handleExport,
    startEdit,
    startFromDesign,
    fromTemplate,
    openAnalytics,
    loadSubTags,
    toggleSubTag,
    handleTabChange,
  }
}
