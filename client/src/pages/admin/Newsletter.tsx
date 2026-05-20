import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Loader2, Plus, Send, Trash2, FileText, Search, Tag as TagIcon, Layout, Calendar, Upload, X, BarChart3, ChevronDown, UserPlus } from 'lucide-react'
import { api } from '../../api/client'
import SectionEditor from '../../components/matcha-work/SectionEditor'

// ── Types ────────────────────────────────────────────────────────────────────

type Subscriber = {
  id: string; email: string; name: string | null; source: string
  status: string; subscribed_at: string; unsubscribed_at: string | null
}

type Newsletter = {
  id: string; title: string; subject: string; status: string
  content_html: string | null; preheader: string | null
  scheduled_at: string | null; sent_at: string | null; created_at: string
  total_sends?: number; total_opened?: number
}

type SubStats = { total: number; active: number; by_source: Record<string, number> }

type Tag = { id: string; slug: string; label: string; description: string | null; subscriber_count: number }

type Template = {
  id: string; name: string; description: string | null
  content_html: string | null; preheader: string | null
  created_at: string; updated_at: string
}

type GrowthPoint = { day: string; subscribed: number; confirmed: number }

type Analytics = {
  attempted: number; sent: number; failed: number
  opened: number; clicked: number
  bounced: number; unsubscribed_window: number
  open_rate: number; click_rate: number; bounce_rate: number; unsubscribe_rate: number
}

type Progress = {
  newsletter_status: string | null
  queued: number; sent: number; failed: number; pending: number
  opened: number; clicked: number; bounced: number
}

type Tab = 'subscribers' | 'newsletters' | 'compose' | 'tags' | 'templates'

// Shared upload helper — both image and video go to the same endpoint;
// the backend keys off file extension and the editor inserts the right tag.
async function uploadNewsletterMedia(file: File): Promise<string | null> {
  const BASE = import.meta.env.VITE_API_URL ?? '/api'
  const token = localStorage.getItem('matcha_access_token')
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await fetch(`${BASE}/admin/newsletter/media/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.url
  } catch {
    return null
  }
}

// ── Page ─────────────────────────────────────────────────────────────────────

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
          const nl = await api.post<Newsletter>('/admin/newsletter/newsletters', {
            title: composeTitle.trim(), subject: composeSubject.trim(),
          })
          setEditingId(nl.id)
          setNewsletters((prev) => prev.some(n => n.id === nl.id) ? prev : [nl, ...prev])
          if (composeHtml || composePreheader) {
            await api.put(`/admin/newsletter/newsletters/${nl.id}`, {
              title: composeTitle.trim(), subject: composeSubject.trim(),
              preheader: composePreheader || undefined,
              content_html: composeHtml || undefined,
            })
          }
        } else {
          await api.put(`/admin/newsletter/newsletters/${editingId}`, {
            title: composeTitle.trim() || undefined,
            subject: composeSubject.trim() || undefined,
            preheader: composePreheader || undefined,
            content_html: composeHtml || undefined,
          })
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
      await api.put(`/admin/newsletter/newsletters/${editingId}`, {
        title: composeTitle.trim() || undefined,
        subject: composeSubject.trim() || undefined,
        preheader: composePreheader || undefined,
        content_html: composeHtml || undefined,
      })
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
    return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-500" size={24} /></div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Newsletter</h1>
        <button
          onClick={() => {
            if (isDirty && !confirm('Discard unsaved changes?')) return
            navigate('/admin/newsletter/composer')
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
        >
          <Plus size={14} /> New Newsletter
        </button>
      </div>

      {/* Stats + growth sparkline */}
      {stats && (
        <div className="flex flex-wrap items-end gap-3 mb-6">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2">
            <p className="text-[10px] text-zinc-500 uppercase">Active</p>
            <p className="text-lg font-bold text-zinc-100">{stats.active}</p>
          </div>
          {Object.entries(stats.by_source).slice(0, 5).map(([src, cnt]) => (
            <div key={src} className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2">
              <p className="text-[10px] text-zinc-500 uppercase">{src}</p>
              <p className="text-lg font-bold text-zinc-100">{cnt}</p>
            </div>
          ))}
          {growth.length > 0 && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2 flex-1 min-w-[280px]">
              <p className="text-[10px] text-zinc-500 uppercase">90-day growth</p>
              <Sparkline points={growth.map((p) => p.subscribed)} />
              <p className="text-[10px] text-zinc-500 mt-1">
                +{growth.reduce((sum, p) => sum + p.subscribed, 0)} in last {growth.length} days
              </p>
            </div>
          )}
        </div>
      )}

      {/* Send progress (sticky banner while sending) */}
      {progress && progress.newsletter_status === 'sending' && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 mb-4 flex items-center gap-3">
          <Loader2 className="animate-spin text-amber-300 shrink-0" size={16} />
          <div className="flex-1">
            <div className="text-xs text-amber-200">
              Sending: {progress.sent} / {progress.queued}
              {progress.failed > 0 && <span className="ml-2 text-red-300">{progress.failed} failed</span>}
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className="h-full bg-amber-400 transition-all"
                style={{ width: `${progress.queued ? Math.round((progress.sent / progress.queued) * 100) : 0}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-zinc-800/60 pb-px">
        {(['subscribers', 'newsletters', 'compose', 'tags', 'templates'] as Tab[]).map((t) => (
          <button key={t} onClick={() => handleTabChange(t)} className={`px-4 py-2 text-xs font-medium transition-colors relative ${tab === t ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
            {t === 'compose' ? (editingId ? 'Edit Draft' : 'Compose') : t.charAt(0).toUpperCase() + t.slice(1)}
            {tab === t && <span className="absolute bottom-0 left-2 right-2 h-px bg-zinc-300 rounded-full" />}
          </button>
        ))}
      </div>

      {/* Subscribers tab */}
      {tab === 'subscribers' && (
        <div>
          <div className="flex items-center justify-between mb-4 gap-3">
            <div className="relative max-w-xs">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..." className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
            </div>
            <div className="flex gap-2">
              <button onClick={() => setImportOpen(true)} className="px-3 py-1.5 text-xs text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded-lg flex items-center gap-1">
                <Upload size={12} /> Import CSV
              </button>
              <button onClick={handleExport} className="px-3 py-1.5 text-xs text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded-lg">Export CSV</button>
            </div>
          </div>
          {managingTagsFor && (
            <div className="fixed inset-0 z-40" onClick={() => setManagingTagsFor(null)} />
          )}
          <div className="rounded-xl border border-zinc-800 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-900/80 border-b border-zinc-800">
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Email</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Name</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Source</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Status</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Groups</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Subscribed</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {filteredSubs.map((s) => (
                  <tr key={s.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    <td className="px-4 py-2.5 text-zinc-200">{s.email}</td>
                    <td className="px-4 py-2.5 text-zinc-400">{s.name || '--'}</td>
                    <td className="px-4 py-2.5"><span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400">{s.source}</span></td>
                    <td className="px-4 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        s.status === 'active' ? 'bg-emerald-900/30 text-emerald-400'
                        : s.status === 'pending' ? 'bg-amber-900/30 text-amber-400'
                        : s.status === 'bounced' ? 'bg-red-900/30 text-red-400'
                        : 'bg-zinc-800 text-zinc-500'
                      }`}>{s.status}</span>
                    </td>
                    <td className="px-4 py-2.5 relative">
                      <div className="flex items-center gap-1 flex-wrap">
                        {(subTagsCache[s.id] ?? []).map(t => (
                          <span key={t.id} className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-700 text-zinc-300">{t.label}</span>
                        ))}
                        <button
                          onClick={async (e) => { e.stopPropagation(); await loadSubTags(s.id); setManagingTagsFor(managingTagsFor === s.id ? null : s.id) }}
                          className="text-zinc-500 hover:text-emerald-400 transition-colors"
                          title="Manage groups"
                        ><TagIcon size={11} /></button>
                      </div>
                      {managingTagsFor === s.id && (
                        <div className="absolute left-0 top-full mt-1 z-50 bg-zinc-900 border border-zinc-700 rounded-lg p-2 shadow-xl min-w-[180px]" onClick={e => e.stopPropagation()}>
                          {tags.length === 0
                            ? <p className="text-[10px] text-zinc-500 px-1 py-0.5">No groups yet. Create one in the Groups tab.</p>
                            : tags.map(t => (
                              <label key={t.id} className="flex items-center gap-2 px-1 py-1 text-[11px] text-zinc-300 cursor-pointer hover:text-zinc-100">
                                <input
                                  type="checkbox"
                                  className="accent-emerald-500"
                                  checked={(subTagsCache[s.id] ?? []).some(st => st.id === t.id)}
                                  onChange={() => toggleSubTag(s.id, t.id)}
                                />
                                {t.label}
                              </label>
                            ))
                          }
                          <button onClick={() => setManagingTagsFor(null)} className="mt-1 w-full text-[10px] text-zinc-500 hover:text-zinc-300 text-right pr-1">Done</button>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-zinc-500">{new Date(s.subscribed_at).toLocaleDateString()}</td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        onClick={() => handleDeleteSubscriber(s.id, s.email)}
                        className="text-zinc-500 hover:text-red-400"
                        title="Delete (GDPR erasure)"
                      ><Trash2 size={13} /></button>
                    </td>
                  </tr>
                ))}
                {filteredSubs.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-500">No subscribers yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Newsletters tab */}
      {tab === 'newsletters' && (
        <div className="space-y-2">
          {newsletters.length === 0 && <p className="text-zinc-500 text-sm py-8 text-center">No newsletters yet.</p>}
          {newsletters.map((nl) => (
            <div key={nl.id} className="flex items-center gap-3 px-4 py-3 rounded-xl border border-zinc-800 hover:bg-zinc-800/20">
              <FileText size={16} className="text-zinc-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-zinc-200 font-medium truncate">{nl.title}</p>
                <p className="text-[11px] text-zinc-500">{nl.subject}</p>
                {nl.scheduled_at && nl.status === 'scheduled' && (
                  <p className="text-[10px] text-amber-300 mt-0.5">
                    Scheduled for {new Date(nl.scheduled_at).toLocaleString()}
                  </p>
                )}
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                nl.status === 'sent' ? 'bg-emerald-900/30 text-emerald-400' :
                nl.status === 'sending' ? 'bg-amber-900/30 text-amber-400' :
                nl.status === 'scheduled' ? 'bg-sky-900/30 text-sky-300' :
                'bg-zinc-800 text-zinc-400'
              }`}>{nl.status}</span>
              {nl.status === 'sent' && (
                <button onClick={() => openAnalytics(nl)} className="text-zinc-500 hover:text-zinc-300 text-xs flex items-center gap-1">
                  <BarChart3 size={12} /> Analytics
                </button>
              )}
              {nl.status === 'draft' && (
                <>
                  <button onClick={() => startEdit(nl)} className="text-zinc-500 hover:text-zinc-300 text-xs">Edit</button>
                  <button onClick={() => handleDelete(nl.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
                </>
              )}
              {nl.status === 'scheduled' && (
                <button
                  onClick={async () => {
                    await api.post(`/admin/newsletter/newsletters/${nl.id}/unschedule`, {})
                    loadData()
                  }}
                  className="text-zinc-500 hover:text-zinc-300 text-xs"
                >
                  Unschedule
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Compose tab — split editor + mobile preview */}
      {tab === 'compose' && (
        <div className="space-y-4">
          {/* Save status indicator */}
          <div className="h-4 flex items-center">
            {saveStatus === 'saving' && <span className="text-[10px] text-zinc-500 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving…</span>}
            {saveStatus === 'saved' && editingId && <span className="text-[10px] text-zinc-500">Saved</span>}
            {saveStatus === 'unsaved' && <span className="text-[10px] text-amber-500">Unsaved changes</span>}
          </div>
          <div className={`grid ${previewViewport === 'wide' ? 'grid-cols-1' : previewViewport === 'desktop' ? 'lg:grid-cols-[1fr_660px]' : 'lg:grid-cols-[1fr_376px]'} gap-6 max-w-6xl`}>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Title</label>
                <input value={composeTitle} onChange={(e) => { setComposeTitle(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} placeholder="Newsletter title..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Subject line</label>
                <input value={composeSubject} onChange={(e) => { setComposeSubject(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} placeholder="Email subject..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  Preheader <span className="text-zinc-600">— inbox preview snippet, hidden in body</span>
                </label>
                <input value={composePreheader} onChange={(e) => { setComposePreheader(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} maxLength={255} placeholder="Short hook seen in the recipient's inbox preview..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Content</label>
                <div className="rounded-lg border border-zinc-700 overflow-hidden" style={{ background: '#1e1e1e' }}>
                  <SectionEditor
                    content={composeHtml}
                    onUpdate={(html) => { setComposeHtml(html); setIsDirty(true); setSaveStatus('unsaved') }}
                    onImageUpload={uploadNewsletterMedia}
                    onVideoUpload={uploadNewsletterMedia}
                  />
                </div>
              </div>
            </div>

            {/* Preview pane */}
            <MobilePreview
              title={composeTitle}
              subject={composeSubject}
              preheader={composePreheader}
              html={composeHtml}
              viewport={previewViewport}
              onViewportChange={setPreviewViewport}
            />
          </div>

          <div className="flex flex-wrap gap-2 max-w-6xl">
            {!editingId ? (
              <button onClick={handleCreate} disabled={saving || !composeTitle.trim() || !composeSubject.trim()} className="flex items-center gap-1.5 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg disabled:opacity-40">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Create Draft
              </button>
            ) : (
              <>
                <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg disabled:opacity-40">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : null} Save Draft
                </button>
                <button onClick={handleTestSend} className="flex items-center gap-1.5 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium rounded-lg border border-zinc-700">
                  <Send size={14} /> Send Test
                </button>
                <button onClick={() => openSend('now')} className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg">
                  <Send size={14} /> Send to all
                </button>
                <button onClick={() => openSend('segment')} className="flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg">
                  <TagIcon size={14} /> Send to segment
                </button>
                <button onClick={() => openSend('schedule')} className="flex items-center gap-1.5 px-4 py-2 bg-sky-700 hover:bg-sky-600 text-white text-sm font-medium rounded-lg">
                  <Calendar size={14} /> Schedule…
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Tags tab */}
      {tab === 'tags' && <TagsTab tags={tags} onChange={async () => { const t = await api.get<{ tags: Tag[] }>('/admin/newsletter/tags'); setTags(t.tags) }} subscribers={subscribers} />}

      {/* Templates tab */}
      {tab === 'templates' && <TemplatesTab templates={templates} onChange={loadData} onPickTemplate={fromTemplate} />}

      {/* Send modal */}
      {sendModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-zinc-100">
                {sendModal.kind === 'now' ? `Send to ${stats?.active ?? 0} subscribers`
                  : sendModal.kind === 'segment' ? 'Send to segment'
                  : 'Schedule send'}
              </h3>
              <button onClick={() => setSendModal(null)} className="text-zinc-500 hover:text-zinc-300"><X size={16} /></button>
            </div>
            {sendModal.kind === 'segment' && (
              <div className="space-y-2 max-h-64 overflow-auto">
                <p className="text-xs text-zinc-500 mb-2">Pick one or more tags. Leave all unchecked to send to everyone.</p>
                {tags.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={sendSegmentTags.includes(t.slug)}
                      onChange={(e) => {
                        if (e.target.checked) setSendSegmentTags((prev) => [...prev, t.slug])
                        else setSendSegmentTags((prev) => prev.filter((s) => s !== t.slug))
                      }}
                      className="accent-emerald-500"
                    />
                    <span className="font-mono text-zinc-400">{t.slug}</span>
                    <span className="text-zinc-500">·</span>
                    <span>{t.label}</span>
                    <span className="ml-auto text-zinc-600">{t.subscriber_count}</span>
                  </label>
                ))}
              </div>
            )}
            {sendModal.kind === 'schedule' && (
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Send at</label>
                <input
                  type="datetime-local"
                  value={sendScheduledAt}
                  onChange={(e) => setSendScheduledAt(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 outline-none focus:border-zinc-500"
                />
                <p className="text-[10px] text-zinc-500 mt-2">
                  Newsletter scheduler beat must be enabled in scheduler_settings (`task_key='newsletter_scheduler'`).
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setSendModal(null)} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">Cancel</button>
              <button onClick={confirmSend} disabled={sending} className="text-xs px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40">
                {sending ? 'Working…' : sendModal.kind === 'schedule' ? 'Schedule' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Analytics drawer */}
      {analyticsOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setAnalyticsOpen(null)}>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-zinc-100">Issue analytics</h3>
              <button onClick={() => setAnalyticsOpen(null)} className="text-zinc-500 hover:text-zinc-300"><X size={16} /></button>
            </div>
            {!analytics ? (
              <Loader2 className="animate-spin text-zinc-500" size={16} />
            ) : (
              <div className="grid grid-cols-2 gap-3 text-xs">
                <Stat label="Sent" value={analytics.sent} />
                <Stat label="Failed" value={analytics.failed} />
                <Stat label="Open rate" value={`${(analytics.open_rate * 100).toFixed(1)}%`} sub={`${analytics.opened} opens`} />
                <Stat label="Click rate" value={`${(analytics.click_rate * 100).toFixed(1)}%`} sub={`${analytics.clicked} unique`} />
                <Stat label="Bounce rate" value={`${(analytics.bounce_rate * 100).toFixed(1)}%`} sub={`${analytics.bounced} bounced`} />
                <Stat label="Unsubscribes" value={analytics.unsubscribed_window} sub="7-day window" />
              </div>
            )}
          </div>
        </div>
      )}

      {importOpen && <CsvImportModal onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); loadData() }} />}
    </div>
  )
}

// ── Mobile preview ──────────────────────────────────────────────────────────

type ViewportKey = 'mobile' | 'desktop' | 'wide'
type ThemeKey = 'dark' | 'light'

const VIEWPORT_WIDTHS: Record<ViewportKey, number> = { mobile: 360, desktop: 640, wide: 800 }

function MobilePreview({ title, subject, preheader, html, viewport, onViewportChange }: {
  title: string; subject: string; preheader: string; html: string
  viewport: ViewportKey; onViewportChange: (v: ViewportKey) => void
}) {
  // Iframe runs the SAME render pipeline as outbound mail — POSTs the draft
  // to /admin/newsletter/preview and inlines whatever the backend produces.
  // That's the only way the preview can stay honest about video poster
  // fallback, branded chrome, theme palette, and CAN-SPAM footer changes.
  const [theme, setTheme] = useState<ThemeKey>('dark')
  const [previewHtml, setPreviewHtml] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setPreviewLoading(true)
    const t = window.setTimeout(async () => {
      try {
        const res = await api.post<{ html: string }>('/admin/newsletter/preview', {
          title, subject, preheader, content_html: html, theme,
        })
        if (!cancelled) setPreviewHtml(res.html || '')
      } catch {
        if (!cancelled) setPreviewHtml('<p style="padding:16px;color:#a00;">Preview failed to render.</p>')
      } finally {
        if (!cancelled) setPreviewLoading(false)
      }
    }, 500)
    return () => { cancelled = true; window.clearTimeout(t) }
  }, [title, subject, preheader, html, theme])

  // Wrap server-rendered fragment in a minimal HTML document. The server
  // returns the email body div; we add a doctype + the recipient-side
  // background that simulates what the email client paints around the email.
  const clientBg = theme === 'dark' ? '#0a0a0a' : '#f3f4f6'
  const previewDoc = `<!doctype html><html><head><meta charset="utf-8"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"><style>
    html,body{margin:0;padding:0;background:${clientBg};}
    body{padding:16px 0;font-family:'Inter',-apple-system,system-ui,sans-serif;}
    img{max-width:100%;height:auto}
    video{max-width:100%;height:auto}
  </style></head><body>${previewHtml || '<p style="padding:16px;color:#777;text-align:center;">Loading preview…</p>'}</body></html>`

  const viewportPx = VIEWPORT_WIDTHS[viewport]

  return (
    <div className="lg:sticky lg:top-4 self-start">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Inbox preview {previewLoading && <Loader2 className="inline-block animate-spin ml-1" size={10} />}</p>
      </div>
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        {(['mobile', 'desktop', 'wide'] as ViewportKey[]).map((v) => (
          <button
            key={v}
            onClick={() => onViewportChange(v)}
            className={`text-[10px] px-2 py-1 rounded ${viewport === v ? 'bg-zinc-700 text-zinc-100' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'}`}
          >
            {v === 'mobile' ? 'Mobile' : v === 'desktop' ? 'Desktop' : 'Wide'} <span className="text-zinc-500">({VIEWPORT_WIDTHS[v]})</span>
          </button>
        ))}
        <div className="w-px h-4 mx-1 bg-zinc-700" />
        {(['dark', 'light'] as ThemeKey[]).map((t) => (
          <button
            key={t}
            onClick={() => setTheme(t)}
            className={`text-[10px] px-2 py-1 rounded ${theme === t ? 'bg-zinc-700 text-zinc-100' : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'}`}
          >
            {t === 'dark' ? 'Dark' : 'Light'}
          </button>
        ))}
      </div>
      <div className="rounded-2xl border-2 border-zinc-800 bg-zinc-900 p-2" style={{ maxWidth: viewportPx + 16 }}>
        <div className="rounded-lg bg-zinc-950 overflow-hidden">
          <div className="px-3 py-2 border-b border-zinc-800">
            <p className="text-[11px] text-zinc-500">Inbox</p>
            <p className="text-xs text-zinc-200 font-medium truncate">{subject || 'Subject…'}</p>
            {preheader && <p className="text-[10px] text-zinc-500 truncate">{preheader}</p>}
          </div>
          <iframe
            title="Newsletter preview"
            sandbox="allow-same-origin"
            srcDoc={previewDoc}
            className="block"
            style={{ width: viewportPx, height: 700, border: 0, background: clientBg }}
          />
        </div>
      </div>
    </div>
  )
}

// ── Tags tab ────────────────────────────────────────────────────────────────

function TagsTab({ tags, onChange, subscribers }: {
  tags: Tag[]
  onChange: () => Promise<void> | void
  subscribers: Subscriber[]
}) {
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [desc, setDesc] = useState('')
  const [expandedTag, setExpandedTag] = useState<string | null>(null)
  const [tagMembers, setTagMembers] = useState<Record<string, { id: string; email: string; name: string | null; status: string }[]>>({})
  const [loadingMembers, setLoadingMembers] = useState<Set<string>>(new Set())
  const [addSearch, setAddSearch] = useState<Record<string, string>>({})

  async function add() {
    if (!slug.trim() || !label.trim()) return
    await api.post('/admin/newsletter/tags', { slug: slug.trim(), label: label.trim(), description: desc.trim() || undefined })
    setSlug(''); setLabel(''); setDesc('')
    await onChange()
  }

  async function remove(id: string) {
    if (!confirm('Delete this tag? Subscribers tagged with it lose the assignment.')) return
    await api.delete(`/admin/newsletter/tags/${id}`)
    if (expandedTag === id) setExpandedTag(null)
    await onChange()
  }

  async function expandTag(tagId: string) {
    if (expandedTag === tagId) { setExpandedTag(null); return }
    setExpandedTag(tagId)
    if (tagMembers[tagId] === undefined) {
      setLoadingMembers(prev => new Set(prev).add(tagId))
      try {
        const res = await api.get<{ subscribers: { id: string; email: string; name: string | null; status: string }[] }>(`/admin/newsletter/tags/${tagId}/subscribers`)
        setTagMembers(prev => ({ ...prev, [tagId]: res.subscribers }))
      } catch {
        setTagMembers(prev => ({ ...prev, [tagId]: [] }))
      } finally {
        setLoadingMembers(prev => { const s = new Set(prev); s.delete(tagId); return s })
      }
    }
  }

  async function removeMemberFromTag(tagId: string, subscriberId: string) {
    try {
      const res = await api.get<{ tags: Tag[] }>(`/admin/newsletter/subscribers/${subscriberId}/tags`)
      const next = res.tags.filter(t => t.id !== tagId).map(t => t.id)
      await api.put(`/admin/newsletter/subscribers/${subscriberId}/tags`, { tag_ids: next })
      setTagMembers(prev => ({ ...prev, [tagId]: (prev[tagId] ?? []).filter(m => m.id !== subscriberId) }))
      await onChange()
    } catch {}
  }

  async function addMemberToTag(tagId: string, sub: Subscriber) {
    try {
      const res = await api.get<{ tags: Tag[] }>(`/admin/newsletter/subscribers/${sub.id}/tags`)
      const alreadyIn = res.tags.some(t => t.id === tagId)
      if (alreadyIn) return
      await api.put(`/admin/newsletter/subscribers/${sub.id}/tags`, { tag_ids: [...res.tags.map(t => t.id), tagId] })
      setTagMembers(prev => ({ ...prev, [tagId]: [...(prev[tagId] ?? []), { id: sub.id, email: sub.email, name: sub.name, status: sub.status }] }))
      setAddSearch(prev => ({ ...prev, [tagId]: '' }))
      await onChange()
    } catch {}
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="rounded-xl border border-zinc-800 p-4">
        <p className="text-xs text-zinc-400 mb-3">Add a tag (slug must be lowercase, no spaces).</p>
        <div className="grid grid-cols-3 gap-2 mb-2">
          <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="slug (e.g. hospitality)" className="px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (e.g. Hospitality)" className="px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
          <button onClick={add} disabled={!slug.trim() || !label.trim()} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg disabled:opacity-40">Add tag</button>
        </div>
        <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
      </div>
      <div className="rounded-xl border border-zinc-800 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900/80 border-b border-zinc-800">
            <tr>
              <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Slug</th>
              <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Label</th>
              <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Description</th>
              <th className="text-right px-4 py-2.5 text-zinc-400 font-medium">Subs</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tags.map((t) => {
              const members = tagMembers[t.id] ?? []
              const search = addSearch[t.id] ?? ''
              const searchResults = search.length >= 1
                ? subscribers.filter(s =>
                    !members.some(m => m.id === s.id) &&
                    (s.email.toLowerCase().includes(search.toLowerCase()) || (s.name || '').toLowerCase().includes(search.toLowerCase()))
                  ).slice(0, 6)
                : []
              return (
                <React.Fragment key={t.id}>
                  <tr
                    className="border-b border-zinc-800/50 hover:bg-zinc-800/20 cursor-pointer"
                    onClick={() => expandTag(t.id)}
                  >
                    <td className="px-4 py-2.5 font-mono text-zinc-300">{t.slug}</td>
                    <td className="px-4 py-2.5 text-zinc-200">{t.label}</td>
                    <td className="px-4 py-2.5 text-zinc-500">{t.description ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-zinc-400">{t.subscriber_count}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center gap-2 justify-end">
                        <ChevronDown
                          size={12}
                          className={`text-zinc-500 transition-transform ${expandedTag === t.id ? 'rotate-180' : ''}`}
                        />
                        <button
                          onClick={(e) => { e.stopPropagation(); remove(t.id) }}
                          className="text-zinc-500 hover:text-red-400"
                          title="Delete tag"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedTag === t.id && (
                    <tr>
                      <td colSpan={5} className="px-4 py-3 bg-zinc-900/40 border-b border-zinc-800/50">
                        {loadingMembers.has(t.id) && (
                          <p className="text-[11px] text-zinc-500 mb-2 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Loading…</p>
                        )}
                        {!loadingMembers.has(t.id) && tagMembers[t.id] !== undefined && members.length === 0 && (
                          <p className="text-[11px] text-zinc-500 mb-2">No members yet.</p>
                        )}
                        {members.length > 0 && (
                          <div className="space-y-1 mb-3">
                            {members.map(m => (
                              <div key={m.id} className="flex items-center gap-2">
                                <span className="text-[11px] text-zinc-300 flex-1">{m.email}</span>
                                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                                  m.status === 'active' ? 'bg-emerald-900/30 text-emerald-400'
                                  : m.status === 'pending' ? 'bg-amber-900/30 text-amber-400'
                                  : 'bg-zinc-800 text-zinc-500'
                                }`}>{m.status}</span>
                                <button
                                  onClick={() => removeMemberFromTag(t.id, m.id)}
                                  className="text-zinc-600 hover:text-red-400"
                                  title="Remove from group"
                                >
                                  <X size={11} />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Add subscriber search */}
                        <div className="relative">
                          <div className="flex items-center gap-2">
                            <UserPlus size={11} className="text-zinc-500 shrink-0" />
                            <input
                              value={search}
                              onChange={(e) => setAddSearch(prev => ({ ...prev, [t.id]: e.target.value }))}
                              placeholder="Add subscriber by email…"
                              className="flex-1 px-2 py-1 rounded border border-zinc-700 bg-zinc-900 text-[11px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-500"
                              onClick={(e) => e.stopPropagation()}
                            />
                          </div>
                          {searchResults.length > 0 && (
                            <div className="absolute left-6 top-full mt-1 z-50 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl w-72">
                              {searchResults.map(s => (
                                <button
                                  key={s.id}
                                  onClick={(e) => { e.stopPropagation(); addMemberToTag(t.id, s) }}
                                  className="w-full text-left px-3 py-2 text-[11px] text-zinc-300 hover:bg-zinc-800 flex items-center gap-2"
                                >
                                  <span className="flex-1 truncate">{s.email}</span>
                                  {s.name && <span className="text-zinc-500 truncate max-w-[100px]">{s.name}</span>}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
            {tags.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-zinc-500">No tags yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Templates tab ───────────────────────────────────────────────────────────

function TemplatesTab({
  templates,
  onChange,
  onPickTemplate,
}: {
  templates: Template[]
  onChange: () => Promise<void> | void
  onPickTemplate: (t: Template) => Promise<void> | void
}) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [pre, setPre] = useState('')
  const [html, setHtml] = useState('')

  async function save() {
    if (!name.trim()) return
    await api.post('/admin/newsletter/templates', {
      name: name.trim(), description: desc || undefined,
      content_html: html || undefined, preheader: pre || undefined,
    })
    setName(''); setDesc(''); setPre(''); setHtml('')
    await onChange()
  }

  async function remove(id: string) {
    if (!confirm('Delete template? Existing newsletters built from it are unaffected.')) return
    await api.delete(`/admin/newsletter/templates/${id}`)
    await onChange()
  }

  return (
    <div className="grid lg:grid-cols-[1fr_360px] gap-6 max-w-6xl">
      <div className="space-y-3">
        <p className="text-xs text-zinc-400">Saved templates seed new newsletters with proven content.</p>
        {templates.length === 0 && <p className="text-zinc-500 text-sm py-4">No templates yet.</p>}
        {templates.map((t) => (
          <div key={t.id} className="rounded-xl border border-zinc-800 px-4 py-3 flex items-center gap-3">
            <Layout size={14} className="text-zinc-500 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-200 truncate">{t.name}</p>
              {t.description && <p className="text-[11px] text-zinc-500 truncate">{t.description}</p>}
            </div>
            <button onClick={() => onPickTemplate(t)} className="text-xs text-emerald-400 hover:text-emerald-300">Use →</button>
            <button onClick={() => remove(t.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-zinc-800 p-4 space-y-3 self-start">
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Save current as template</p>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
        <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
        <input value={pre} onChange={(e) => setPre(e.target.value)} placeholder="Preheader (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
        <textarea value={html} onChange={(e) => setHtml(e.target.value)} placeholder="Paste sanitized HTML or leave blank for an empty starter" rows={5} className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-xs font-mono text-zinc-200 placeholder-zinc-500 outline-none" />
        <button onClick={save} disabled={!name.trim()} className="w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg disabled:opacity-40">Save template</button>
      </div>
    </div>
  )
}

// ── CSV import ──────────────────────────────────────────────────────────────

function CsvImportModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [csv, setCsv] = useState('')
  const [busy, setBusy] = useState(false)

  function parseCsv(): { email: string; name?: string }[] {
    // Handles quoted fields with embedded commas + escaped doubled quotes,
    // e.g.: '"Sam, Jr.",sam@x.com' → ['Sam, Jr.', 'sam@x.com'].
    function parseRow(row: string): string[] {
      const out: string[] = []
      let cur = ''
      let inQuotes = false
      for (let i = 0; i < row.length; i++) {
        const ch = row[i]
        if (inQuotes) {
          if (ch === '"') {
            if (row[i + 1] === '"') { cur += '"'; i++ } // escaped ""
            else inQuotes = false
          } else {
            cur += ch
          }
        } else if (ch === '"') {
          inQuotes = true
        } else if (ch === ',') {
          out.push(cur)
          cur = ''
        } else {
          cur += ch
        }
      }
      out.push(cur)
      return out.map((p) => p.trim())
    }

    const rows = csv.replace(/\r\n/g, '\n').split('\n').map((r) => r.trim()).filter(Boolean)
    if (!rows.length) return []
    const start = rows[0].toLowerCase().includes('email') ? 1 : 0
    return rows.slice(start)
      .map(parseRow)
      .filter((parts) => parts.length >= 1)
      .map((parts) => ({ email: (parts[0] || '').toLowerCase(), name: parts[1] || undefined }))
      .filter((p) => p.email.includes('@'))
  }

  async function submit() {
    const emails = parseCsv()
    if (emails.length === 0) {
      alert('No valid emails parsed.')
      return
    }
    setBusy(true)
    try {
      const res = await api.post<{ imported: number }>('/admin/newsletter/subscribers/import', { emails })
      alert(`Imported ${res.imported} subscriber(s).`)
      onDone()
    } catch (err) {
      alert(`Import failed: ${(err as Error).message}`)
    }
    setBusy(false)
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-100">Import subscribers</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={16} /></button>
        </div>
        <p className="text-xs text-zinc-500 mb-3">
          Paste CSV. First column = email, optional second column = name. Header row optional. Up to 500 rows per import.
        </p>
        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          placeholder={'email,name\nsam@example.com,Sam Lee\nalex@example.com,Alex Park'}
          rows={10}
          className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-xs font-mono text-zinc-200 placeholder-zinc-500 outline-none"
        />
        <p className="text-[10px] text-zinc-500 mt-2">Detected: {parseCsv().length} valid email(s)</p>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={submit} disabled={busy || parseCsv().length === 0} className="text-xs px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40">
            {busy ? 'Importing…' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Sparkline ───────────────────────────────────────────────────────────────

function Sparkline({ points }: { points: number[] }) {
  if (points.length === 0) return null
  const max = Math.max(...points, 1)
  const w = 240
  const h = 32
  const step = points.length > 1 ? w / (points.length - 1) : 0
  const path = points
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(1)} ${(h - (v / max) * h).toFixed(1)}`)
    .join(' ')
  return (
    <svg width={w} height={h} className="block">
      <path d={path} stroke="#34d399" strokeWidth={1.5} fill="none" />
    </svg>
  )
}

function Stat({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-semibold text-zinc-100">{value}</p>
      {sub && <p className="text-[10px] text-zinc-500 mt-0.5">{sub}</p>}
    </div>
  )
}
