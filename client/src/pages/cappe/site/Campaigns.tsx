import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Mail, Send } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell from '../../../components/cappe/SurfaceShell'
import type { CappeCampaign } from '../../../types/cappe'

const statusStyle: Record<string, string> = {
  draft: 'bg-zinc-800 text-zinc-400',
  scheduled: 'bg-sky-500/15 text-sky-400',
  sending: 'bg-amber-500/15 text-amber-400',
  sent: 'bg-emerald-500/15 text-emerald-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
}

export default function Campaigns() {
  const { siteId } = useParams<{ siteId: string }>()
  const [campaigns, setCampaigns] = useState<CappeCampaign[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const [form, setForm] = useState({ subject: '', body_html: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    cappeApi
      .get<CappeCampaign[]>(`/sites/${siteId}/campaigns`)
      .then(setCampaigns)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load campaigns'))
  }, [siteId])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    if (!form.subject.trim()) return
    setSaving(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappeCampaign>(`/sites/${siteId}/campaigns`, {
        subject: form.subject.trim(),
        body_html: form.body_html.trim() || null,
      })
      setCampaigns((c) => [created, ...(c || [])])
      setForm({ subject: '', body_html: '' })
      setComposing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create campaign')
    } finally {
      setSaving(false)
    }
  }

  async function send(c: CappeCampaign) {
    if (!confirm(`Send "${c.subject}" now? (Sending is stubbed — no email actually goes out yet.)`)) return
    try {
      const updated = await cappeApi.post<CappeCampaign>(`/sites/${siteId}/campaigns/${c.id}/send`)
      setCampaigns((list) => (list || []).map((x) => (x.id === c.id ? updated : x)))
      setNotice(`Marked sent — ${updated.recipient_count} deliverable recipient(s). (No email sent: sending is stubbed.)`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send')
    }
  }

  async function remove(id: string) {
    await cappeApi.delete(`/sites/${siteId}/campaigns/${id}`)
    setCampaigns((c) => (c || []).filter((x) => x.id !== id))
  }

  return (
    <SurfaceShell
      title="Campaigns"
      subtitle="Compose newsletters to your subscribers."
      actions={
        <button
          onClick={() => setComposing((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"
        >
          <Plus className="h-4 w-4" /> New campaign
        </button>
      }
    >
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {notice && <p className="mb-4 text-sm text-emerald-400">{notice}</p>}

      {composing && (
        <form onSubmit={create} className="mb-6 space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
          <input
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
            placeholder="Subject"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500"
          />
          <textarea
            value={form.body_html}
            onChange={(e) => setForm({ ...form, body_html: e.target.value })}
            placeholder="Body (HTML allowed)"
            rows={6}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500"
          />
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Save draft
          </button>
        </form>
      )}

      {campaigns === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : campaigns.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Mail className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No campaigns yet.
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
          {campaigns.map((c) => (
            <div key={c.id} className="flex items-center gap-4 px-5 py-3">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-zinc-100">{c.subject}</div>
                <div className="text-xs text-zinc-400">
                  {c.status === 'sent' && c.sent_at
                    ? `Sent ${new Date(c.sent_at).toLocaleDateString()} · ${c.recipient_count} recipients`
                    : `Created ${new Date(c.created_at).toLocaleDateString()}`}
                </div>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[c.status]}`}>{c.status}</span>
              {c.status !== 'sent' && c.status !== 'sending' && (
                <button onClick={() => send(c)} className="flex items-center gap-1 text-xs font-medium text-emerald-400 hover:underline">
                  <Send className="h-3.5 w-3.5" /> Send
                </button>
              )}
              <button onClick={() => remove(c.id)} className="text-zinc-400 hover:text-red-400">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
