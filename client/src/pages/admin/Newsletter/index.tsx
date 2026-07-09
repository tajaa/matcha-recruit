import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../../../api/client'
import type { Subscriber, Newsletter, SubStats, Tag, Template, GrowthPoint, Analytics, Progress, Tab } from './types'
import { Sparkline } from './Sparkline'
import { SubscribersTab } from './SubscribersTab'
import { NewslettersTab } from './NewslettersTab'
import { ComposeTab } from './ComposeTab'
import { TagsTab } from './TagsTab'
import { TemplatesTab } from './TemplatesTab'
import { SendModal } from './SendModal'
import { AnalyticsDrawer } from './AnalyticsDrawer'
import { CsvImportModal } from './CsvImportModal'
import type { ViewportKey } from './MobilePreview'

export default function NewsletterAdmin() {
  const navigate = useNavigate()
  const location = useLocation()
  const [tab, setTab] = useState<Tab>('subscribers')
  const [subscribers, setSubs] = useState<Subscriber[]>([])
  const [stats, setStats] = useState<SubStats | null>(null)
  const [newsletters, setNewsletters] = useState<Newsletter[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [growth, setGrowth] = useState<GrowthPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  // Compose state
  const [composeTitle, setComposeTitle] = useState('')
  const [composeSubject, setComposeSubject] = useState('')
  const [composePreheader, setComposePreheader] = useState('')
  const [composeHtml, setComposeHtml] = useState('')
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
      setIsDirty(false); setSaveStatus('saved')
    }
  }, [location.pathname])

  async function loadData() {
    setLoading(true)
    try {
      const [subRes, nlRes, tagsRes, tplRes, growthRes] = await Promise.allSettled([
        api.get<{ subscribers: Subscriber[]; total: number; stats: SubStats }>('/admin/newsletter/subscribers?limit=100'),
        api.get<Newsletter[]>('/admin/newsletter/newsletters'),
        api.get<{ tags: Tag[] }>('/admin/newsletter/tags'),
        api.get<{ templates: Template[] }>('/admin/newsletter/templates'),
        api.get<{ days: number; series: GrowthPoint[] }>('/admin/newsletter/subscribers/growth?days=90'),
      ])
      if (subRes.status === 'fulfilled') {
        setSubs(subRes.value.subscribers)
        setStats(subRes.value.stats)
      }
      if (nlRes.status === 'fulfilled') setNewsletters(nlRes.value)
      if (tagsRes.status === 'fulfilled') setTags(tagsRes.value.tags)
      if (tplRes.status === 'fulfilled') setTemplates(tplRes.value.templates)
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

  // Auto-save: 2s after last keystroke, create or update draft
  useEffect(() => {
    if (!isDirty) return
    const canCreate = composeTitle.trim() && composeSubject.trim()
    if (!editingId && !canCreate) return
    setSaveStatus('saving')
    const timer = window.setTimeout(async () => {
      try {
        if (!editingId) {
          const created = await api.post<Newsletter>('/admin/newsletter/newsletters', {
            title: composeTitle.trim(), subject: composeSubject.trim(),
          })
          setEditingId(created.id)
          let saved = created
          if (composeHtml || composePreheader) {
            saved = await api.put<Newsletter>(`/admin/newsletter/newsletters/${created.id}`, {
              title: composeTitle.trim(), subject: composeSubject.trim(),
              preheader: composePreheader || undefined,
              content_html: composeHtml || undefined,
            })
          }
          upsertNewsletter(saved)
        } else {
          const saved = await api.put<Newsletter>(`/admin/newsletter/newsletters/${editingId}`, {
            title: composeTitle.trim() || undefined,
            subject: composeSubject.trim() || undefined,
            preheader: composePreheader || undefined,
            content_html: composeHtml || undefined,
          })
          upsertNewsletter(saved)
        }
        setIsDirty(false)
        setSaveStatus('saved')
      } catch {
        setSaveStatus('unsaved')
      }
    }, 2000)
    return () => window.clearTimeout(timer)
  }, [composeTitle, composeSubject, composePreheader, composeHtml, isDirty])

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
      const saved = await api.put<Newsletter>(`/admin/newsletter/newsletters/${editingId}`, {
        title: composeTitle.trim() || undefined,
        subject: composeSubject.trim() || undefined,
        preheader: composePreheader || undefined,
        content_html: composeHtml || undefined,
      })
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
    setIsDirty(false)
    setSaveStatus('saved')
    setTab('compose')
  }

  async function fromTemplate(t: Template) {
    setComposeTitle(t.name)
    setComposeSubject(t.name)
    setComposePreheader(t.preheader ?? '')
    setComposeHtml(t.content_html ?? '')
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

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-slate-400" size={24} /></div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Newsletter</h1>
        <button
          onClick={() => {
            if (isDirty && !confirm('Discard unsaved changes?')) return
            navigate('/admin/newsletter/composer')
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg shadow-sm transition-colors"
        >
          <Plus size={14} /> New Newsletter
        </button>
      </div>

      {/* Stats + growth sparkline */}
      {stats && (
        <div className="flex flex-wrap items-end gap-3 mb-6">
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm px-4 py-2">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Active</p>
            <p className="text-lg font-bold text-slate-900">{stats.active}</p>
          </div>
          {Object.entries(stats.by_source).slice(0, 5).map(([src, cnt]) => (
            <div key={src} className="rounded-lg border border-slate-200 bg-white shadow-sm px-4 py-2">
              <p className="text-[10px] text-slate-400 uppercase tracking-wide">{src}</p>
              <p className="text-lg font-bold text-slate-900">{cnt}</p>
            </div>
          ))}
          {growth.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white shadow-sm px-4 py-2 flex-1 min-w-[280px]">
              <p className="text-[10px] text-slate-400 uppercase tracking-wide">90-day growth</p>
              <Sparkline points={growth.map((p) => p.subscribed)} />
              <p className="text-[10px] text-slate-400 mt-1">
                +{growth.reduce((sum, p) => sum + p.subscribed, 0)} in last {growth.length} days
              </p>
            </div>
          )}
        </div>
      )}

      {/* Send progress (sticky banner while sending) */}
      {progress && progress.newsletter_status === 'sending' && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 mb-4 flex items-center gap-3">
          <Loader2 className="animate-spin text-amber-600 shrink-0" size={16} />
          <div className="flex-1">
            <div className="text-xs text-amber-800">
              Sending: {progress.sent} / {progress.queued}
              {progress.failed > 0 && <span className="ml-2 text-red-600">{progress.failed} failed</span>}
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-amber-100 overflow-hidden">
              <div
                className="h-full bg-amber-500 transition-all"
                style={{ width: `${progress.queued ? Math.round((progress.sent / progress.queued) * 100) : 0}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-200 pb-px">
        {(['subscribers', 'newsletters', 'compose', 'tags', 'templates'] as Tab[]).map((t) => {
          const draftCount = t === 'newsletters' ? newsletters.filter(n => n.status === 'draft').length : 0
          return (
            <button key={t} onClick={() => handleTabChange(t)} className={`px-4 py-2 text-xs font-medium transition-colors relative flex items-center gap-1.5 ${tab === t ? 'text-slate-900' : 'text-slate-500 hover:text-slate-800'}`}>
              {t === 'compose' ? (editingId ? 'Edit Draft' : 'Compose') : t.charAt(0).toUpperCase() + t.slice(1)}
              {draftCount > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-500 font-mono leading-none">{draftCount}</span>
              )}
              {tab === t && <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-emerald-600 rounded-full" />}
            </button>
          )
        })}
      </div>

      {/* Subscribers tab */}
      {tab === 'subscribers' && (
        <SubscribersTab
          search={search} onSearchChange={setSearch}
          filteredSubs={filteredSubs}
          tags={tags}
          subTagsCache={subTagsCache}
          managingTagsFor={managingTagsFor} onManagingTagsForChange={setManagingTagsFor}
          onImportOpen={() => setImportOpen(true)}
          onExport={handleExport}
          onLoadSubTags={loadSubTags}
          onToggleSubTag={toggleSubTag}
          onDeleteSubscriber={handleDeleteSubscriber}
        />
      )}

      {/* Newsletters tab */}
      {tab === 'newsletters' && (
        <NewslettersTab
          newsletters={newsletters}
          onEdit={startEdit}
          onDelete={handleDelete}
          onOpenAnalytics={openAnalytics}
          onReload={loadData}
        />
      )}

      {/* Compose tab — split editor + mobile preview */}
      {tab === 'compose' && (
        <ComposeTab
          saveStatus={saveStatus}
          editingId={editingId}
          composeTitle={composeTitle} setComposeTitle={setComposeTitle}
          composeSubject={composeSubject} setComposeSubject={setComposeSubject}
          composePreheader={composePreheader} setComposePreheader={setComposePreheader}
          composeHtml={composeHtml} setComposeHtml={setComposeHtml}
          setIsDirty={setIsDirty} setSaveStatus={setSaveStatus}
          previewViewport={previewViewport} setPreviewViewport={setPreviewViewport}
          saving={saving}
          handleCreate={handleCreate}
          handleSave={handleSave}
          handleTestSend={handleTestSend}
          openSend={openSend}
        />
      )}

      {/* Tags tab */}
      {tab === 'tags' && <TagsTab tags={tags} onChange={async () => { const t = await api.get<{ tags: Tag[] }>('/admin/newsletter/tags'); setTags(t.tags) }} subscribers={subscribers} />}

      {/* Templates tab */}
      {tab === 'templates' && <TemplatesTab templates={templates} onChange={loadData} onPickTemplate={fromTemplate} />}

      {/* Send modal */}
      {sendModal && (
        <SendModal
          sendModal={sendModal} setSendModal={setSendModal}
          tags={tags} stats={stats}
          sendSegmentTags={sendSegmentTags} setSendSegmentTags={setSendSegmentTags}
          sendScheduledAt={sendScheduledAt} setSendScheduledAt={setSendScheduledAt}
          sending={sending} confirmSend={confirmSend}
        />
      )}

      {/* Analytics drawer */}
      {analyticsOpen && (
        <AnalyticsDrawer setAnalyticsOpen={setAnalyticsOpen} analytics={analytics} />
      )}

      {importOpen && <CsvImportModal onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); loadData() }} />}
    </div>
  )
}
