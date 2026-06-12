import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Users } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell from '../../../components/cappe/SurfaceShell'
import type { CappeSubscriber } from '../../../types/cappe'

const statusStyle: Record<string, string> = {
  subscribed: 'bg-emerald-100 text-emerald-700',
  unsubscribed: 'bg-zinc-100 text-zinc-500',
  bounced: 'bg-red-100 text-red-700',
  pending: 'bg-amber-100 text-amber-700',
}

export default function Subscribers() {
  const { siteId } = useParams<{ siteId: string }>()
  const [subs, setSubs] = useState<CappeSubscriber[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ email: '', name: '' })
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    cappeApi
      .get<CappeSubscriber[]>(`/sites/${siteId}/subscribers`)
      .then(setSubs)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load subscribers'))
  }, [siteId])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!form.email.trim()) return
    setAdding(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappeSubscriber>(`/sites/${siteId}/subscribers`, {
        email: form.email.trim(),
        name: form.name.trim() || null,
        source: 'manual',
      })
      setSubs((s) => [created, ...(s || [])])
      setForm({ email: '', name: '' })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add subscriber')
    } finally {
      setAdding(false)
    }
  }

  async function remove(id: string) {
    await cappeApi.delete(`/sites/${siteId}/subscribers/${id}`)
    setSubs((s) => (s || []).filter((x) => x.id !== id))
  }

  const activeCount = (subs || []).filter((s) => s.status === 'subscribed').length

  return (
    <SurfaceShell title="Subscribers" subtitle={subs ? `${activeCount} active of ${subs.length}` : 'Newsletter list.'}>
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      <form onSubmit={add} className="mb-6 flex flex-wrap gap-2 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
        <input
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder="email@example.com"
          type="email"
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Name (optional)"
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <button
          type="submit"
          disabled={adding}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add
        </button>
      </form>

      {subs === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : subs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 py-12 text-center text-sm text-zinc-500">
          <Users className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No subscribers yet.
        </div>
      ) : (
        <div className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white">
          {subs.map((s) => (
            <div key={s.id} className="flex items-center gap-4 px-5 py-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-zinc-900">{s.email}</div>
                {s.name && <div className="text-xs text-zinc-400">{s.name}</div>}
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[s.status]}`}>{s.status}</span>
              <button onClick={() => remove(s.id)} className="text-zinc-400 hover:text-red-600">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
