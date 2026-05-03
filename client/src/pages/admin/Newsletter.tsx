import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Plus, Send, Trash2, FileText, Search, Tag as TagIcon, Layout, Calendar, Upload, X, BarChart3 } from 'lucide-react'
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
  opened: number; clicked_unique: number; clicked_total: number
  bounced: number; unsubscribed_window: number
  open_rate: number; click_rate: number; bounce_rate: number; unsubscribe_rate: number
}

type Progress = {
  newsletter_status: string | null
  queued: number; sent: number; failed: number; pending: number
  opened: number; clicked: number; bounced: number
}

type Tab = 'subscribers' | 'newsletters' | 'compose' | 'tags' | 'templates'

// ── Page ─────────────────────────────────────────────────────────────────────

export default function NewsletterAdmin() {
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

  // Send modal state
  const [sendModal, setSendModal] = useState<{ kind: 'now' | 'schedule' | 'segment' } | null>(null)
  const [sendSegmentTags, setSendSegmentTags] = useState<string[]>([])
  const [sendScheduledAt, setSendScheduledAt] = useState('')
  const [sending, setSending] = useState(false)

  // Live progress for the in-flight newsletter (polled while sending).
  const [progress, setProgress] = useState<Progress | null>(null)
  const progressTargetRef = useRef<string | null>(null)

  // Per-newsletter analytics drawer
  const [analyticsOpen, setAnalyticsOpen] = useState<string | null>(null)
  const [analytics, setAnalytics] = useState<Analytics | null>(null)

  // CSV import
  const [importOpen, setImportOpen] = useState(false)

  useEffect(() => { loadData() }, [])

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
  useEffect(() => {
    const target = progressTargetRef.current
    if (!target) return
    let stopped = false
    async function tick() {
      while (!stopped) {
        try {
          const p = await api.get<Progress>(`/admin/newsletter/newsletters/${target}/progress`)
          setProgress(p)
          if (p.newsletter_status !== 'sending') {
            stopped = true
            // Reload list so the freshly-sent row appears with final stats.
            loadData()
            return
          }
        } catch {}
        await new Promise((r) => setTimeout(r, 3000))
      }
    }
    tick()
    return () => { stopped = true }
  }, [progress?.newsletter_status])

  async function handleCreate() {
    if (!composeTitle.trim() || !composeSubject.trim()) return
    setSaving(true)
    try {
      const nl = await api.post<Newsletter>('/admin/newsletter/newsletters', {
        title: composeTitle.trim(), subject: composeSubject.trim(),
      })
      setEditingId(nl.id)
      setNewsletters((prev) => [nl, ...prev])
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
    setTab('compose')
  }

  async function fromTemplate(t: Template) {
    setComposeTitle(t.name)
    setComposeSubject(t.name)
    setComposePreheader(t.preheader ?? '')
    setComposeHtml(t.content_html ?? '')
    setEditingId(null)
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

  const filteredSubs = useMemo(() => subscribers.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.email.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q)
  }), [subscribers, search])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-500" size={24} /></div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Newsletter</h1>
        <button
          onClick={() => { setEditingId(null); setComposeTitle(''); setComposeSubject(''); setComposePreheader(''); setComposeHtml(''); setTab('compose') }}
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
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-xs font-medium transition-colors relative ${tab === t ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
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
          <div className="rounded-xl border border-zinc-800 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-900/80 border-b border-zinc-800">
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Email</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Name</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Source</th>
                  <th className="text-left px-4 py-2.5 text-zinc-400 font-medium">Status</th>
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
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-500">No subscribers yet</td></tr>
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
          <div className="grid lg:grid-cols-[1fr_360px] gap-6 max-w-6xl">
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Title</label>
                <input value={composeTitle} onChange={(e) => setComposeTitle(e.target.value)} placeholder="Newsletter title..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Subject line</label>
                <input value={composeSubject} onChange={(e) => setComposeSubject(e.target.value)} placeholder="Email subject..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  Preheader <span className="text-zinc-600">— inbox preview snippet, hidden in body</span>
                </label>
                <input value={composePreheader} onChange={(e) => setComposePreheader(e.target.value)} maxLength={255} placeholder="Short hook seen in the recipient's inbox preview..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Content</label>
                <div className="rounded-lg border border-zinc-700 overflow-hidden" style={{ background: '#1e1e1e' }}>
                  <SectionEditor
                    content={composeHtml}
                    onUpdate={(html) => setComposeHtml(html)}
                    onImageUpload={async (file) => {
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
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Mobile preview pane */}
            <MobilePreview
              title={composeTitle}
              subject={composeSubject}
              preheader={composePreheader}
              html={composeHtml}
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
      {tab === 'tags' && <TagsTab tags={tags} onChange={async () => { const t = await api.get<{ tags: Tag[] }>('/admin/newsletter/tags'); setTags(t.tags) }} />}

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
                <Stat label="Click rate" value={`${(analytics.click_rate * 100).toFixed(1)}%`} sub={`${analytics.clicked_unique} unique`} />
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

function MobilePreview({ title, subject, preheader, html }: { title: string; subject: string; preheader: string; html: string }) {
  return (
    <div className="lg:sticky lg:top-4 self-start">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Mobile preview</p>
      <div className="rounded-2xl border-2 border-zinc-800 bg-zinc-900 p-2 max-w-[360px]">
        <div className="rounded-lg bg-[#1e1e1e] overflow-hidden">
          <div className="px-3 py-2 border-b border-zinc-800">
            <p className="text-[11px] text-zinc-500">Inbox</p>
            <p className="text-xs text-zinc-200 font-medium truncate">{subject || 'Subject…'}</p>
            {preheader && <p className="text-[10px] text-zinc-500 truncate">{preheader}</p>}
          </div>
          <div className="px-4 py-4 max-h-[600px] overflow-auto">
            <p className="text-amber-300 text-base font-bold mb-3">Matcha</p>
            <h2 className="text-zinc-100 text-base font-semibold mb-3">{title || '(title)'}</h2>
            <div
              className="text-zinc-300 text-xs leading-relaxed prose prose-invert prose-sm max-w-none"
              dangerouslySetInnerHTML={{ __html: html || '<p class="text-zinc-600">(content goes here)</p>' }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Tags tab ────────────────────────────────────────────────────────────────

function TagsTab({ tags, onChange }: { tags: Tag[]; onChange: () => Promise<void> | void }) {
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [desc, setDesc] = useState('')

  async function add() {
    if (!slug.trim() || !label.trim()) return
    await api.post('/admin/newsletter/tags', { slug: slug.trim(), label: label.trim(), description: desc.trim() || undefined })
    setSlug(''); setLabel(''); setDesc('')
    await onChange()
  }

  async function remove(id: string) {
    if (!confirm('Delete this tag? Subscribers tagged with it lose the assignment.')) return
    await api.delete(`/admin/newsletter/tags/${id}`)
    await onChange()
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
            {tags.map((t) => (
              <tr key={t.id} className="border-b border-zinc-800/50">
                <td className="px-4 py-2.5 font-mono text-zinc-300">{t.slug}</td>
                <td className="px-4 py-2.5 text-zinc-200">{t.label}</td>
                <td className="px-4 py-2.5 text-zinc-500">{t.description ?? '—'}</td>
                <td className="px-4 py-2.5 text-right text-zinc-400">{t.subscriber_count}</td>
                <td className="px-4 py-2.5 text-right">
                  <button onClick={() => remove(t.id)} className="text-zinc-500 hover:text-red-400" title="Delete tag">
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
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
    const rows = csv.trim().split(/\r?\n/).filter(Boolean)
    if (!rows.length) return []
    // Skip header row if it looks like one.
    const start = rows[0].toLowerCase().includes('email') ? 1 : 0
    return rows.slice(start).map((row) => {
      const parts = row.split(',').map((p) => p.trim().replace(/^"|"$/g, ''))
      return { email: parts[0], name: parts[1] || undefined }
    }).filter((p) => p.email && p.email.includes('@'))
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
