import { useEffect, useState } from 'react'
import { Loader2, Plus, Send, Trash2, FileText, Search } from 'lucide-react'
import { api } from '../../api/client'
import SectionEditor from '../../components/matcha-work/SectionEditor'

type Subscriber = {
  id: string; email: string; name: string | null; source: string
  status: string; subscribed_at: string; unsubscribed_at: string | null
}

type Newsletter = {
  id: string; title: string; subject: string; status: string
  content_html: string | null; sent_at: string | null; created_at: string
  total_sends?: number; total_opened?: number
  send_stats?: { total: number; sent: number; opened: number; clicked: number; bounced: number }
}

type SubStats = { total: number; active: number; by_source: Record<string, number> }

export default function NewsletterAdmin() {
  const [tab, setTab] = useState<'subscribers' | 'newsletters' | 'compose'>('subscribers')
  const [subscribers, setSubs] = useState<Subscriber[]>([])
  const [stats, setStats] = useState<SubStats | null>(null)
  const [newsletters, setNewsletters] = useState<Newsletter[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  // Compose state
  const [composeTitle, setComposeTitle] = useState('')
  const [composeSubject, setComposeSubject] = useState('')
  const [composeHtml, setComposeHtml] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [subRes, nlRes] = await Promise.allSettled([
        api.get<{ subscribers: Subscriber[]; total: number; stats: SubStats }>('/admin/newsletter/subscribers?limit=100'),
        api.get<Newsletter[]>('/admin/newsletter/newsletters'),
      ])
      if (subRes.status === 'fulfilled') {
        setSubs(subRes.value.subscribers)
        setStats(subRes.value.stats)
      }
      if (nlRes.status === 'fulfilled') setNewsletters(nlRes.value)
    } catch {}
    setLoading(false)
  }

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
        content_html: composeHtml || undefined,
      })
    } catch {}
    setSaving(false)
  }

  async function handleSend() {
    if (!editingId) return
    const audience = stats?.active ?? 0
    if (!confirm(`Send "${composeSubject}" to ${audience} active subscriber${audience === 1 ? '' : 's'}? This cannot be undone.`)) {
      return
    }
    setSending(true)
    try {
      await handleSave()
      const result = await api.post<{ queued: number; status: string }>(`/admin/newsletter/newsletters/${editingId}/send`)
      alert(`Queued for ${result.queued} subscribers. Sending in the background.`)
      setEditingId(null)
      setComposeTitle('')
      setComposeSubject('')
      setComposeHtml('')
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
    if (!confirm('Soft-delete this draft? It will be hidden but kept for audit.')) return
    try {
      await api.delete(`/admin/newsletter/newsletters/${id}`)
      setNewsletters((prev) => prev.filter((n) => n.id !== id))
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`)
    }
  }

  async function handleDeleteSubscriber(id: string, email: string) {
    if (!confirm(`Permanently delete subscriber ${email}? GDPR right-to-erasure — cannot be undone.`)) return
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
    setComposeHtml(nl.content_html || '')
    setTab('compose')
  }

  const filteredSubs = subscribers.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.email.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q)
  })

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-500" size={24} /></div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Newsletter</h1>
        <button
          onClick={() => { setEditingId(null); setComposeTitle(''); setComposeSubject(''); setComposeHtml(''); setTab('compose') }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
        >
          <Plus size={14} /> New Newsletter
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="flex gap-3 mb-6">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2">
            <p className="text-[10px] text-zinc-500 uppercase">Active</p>
            <p className="text-lg font-bold text-zinc-100">{stats.active}</p>
          </div>
          {Object.entries(stats.by_source).map(([src, cnt]) => (
            <div key={src} className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2">
              <p className="text-[10px] text-zinc-500 uppercase">{src}</p>
              <p className="text-lg font-bold text-zinc-100">{cnt}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-zinc-800/60 pb-px">
        {(['subscribers', 'newsletters', 'compose'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-xs font-medium transition-colors relative ${tab === t ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
            {t === 'compose' ? (editingId ? 'Edit Draft' : 'Compose') : t.charAt(0).toUpperCase() + t.slice(1)}
            {tab === t && <span className="absolute bottom-0 left-2 right-2 h-px bg-zinc-300 rounded-full" />}
          </button>
        ))}
      </div>

      {/* Subscribers tab */}
      {tab === 'subscribers' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div className="relative max-w-xs">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..." className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
            </div>
            <button onClick={handleExport} className="px-3 py-1.5 text-xs text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded-lg">Export CSV</button>
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
          {newsletters.length === 0 && <p className="text-zinc-500 text-sm py-8 text-center">No newsletters yet. Create your first one.</p>}
          {newsletters.map((nl) => (
            <div key={nl.id} className="flex items-center gap-3 px-4 py-3 rounded-xl border border-zinc-800 hover:bg-zinc-800/20">
              <FileText size={16} className="text-zinc-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-zinc-200 font-medium truncate">{nl.title}</p>
                <p className="text-[11px] text-zinc-500">{nl.subject}</p>
              </div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                nl.status === 'sent' ? 'bg-emerald-900/30 text-emerald-400' :
                nl.status === 'sending' ? 'bg-amber-900/30 text-amber-400' :
                'bg-zinc-800 text-zinc-400'
              }`}>{nl.status}</span>
              {nl.total_sends != null && (
                <span className="text-[10px] text-zinc-500">{nl.total_sends} sent{nl.total_opened ? `, ${nl.total_opened} opened` : ''}</span>
              )}
              {nl.status === 'draft' && (
                <>
                  <button onClick={() => startEdit(nl)} className="text-zinc-500 hover:text-zinc-300 text-xs">Edit</button>
                  <button onClick={() => handleDelete(nl.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Compose tab */}
      {tab === 'compose' && (
        <div className="space-y-4 max-w-5xl">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Title</label>
            <input value={composeTitle} onChange={(e) => setComposeTitle(e.target.value)} placeholder="Newsletter title..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Subject line</label>
            <input value={composeSubject} onChange={(e) => setComposeSubject(e.target.value)} placeholder="Email subject..." className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
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
          <div className="flex gap-2">
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
                <button onClick={handleSend} disabled={sending} className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg disabled:opacity-40">
                  {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Send to {stats?.active ?? 0} subscribers
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
