import { useCallback, useEffect, useState } from 'react'
import { Loader2, X, Plus, Trash2 } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import type { CappeDnsRecord } from '../../types/cappe'

const TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'CAA', 'NS', 'ALIAS', 'SRV'] as const
const input =
  'rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500'

type Draft = { type: string; name: string; content: string; ttl: string; prio: string }
const EMPTY: Draft = { type: 'A', name: '', content: '', ttl: '600', prio: '' }

/** DNS-record manager for a domain registered through us (Porkbun). Add/delete
 *  A/CNAME/MX/TXT etc. so tenants can wire email + verifications themselves. */
export default function DnsRecordsModal({ domainId, domain, onClose }: {
  domainId: string
  domain: string
  onClose: () => void
}) {
  const [records, setRecords] = useState<CappeDnsRecord[] | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    cappeApi.get<CappeDnsRecord[]>(`/domains/${domainId}/dns`).then(setRecords).catch((e) => {
      setError(e instanceof Error ? e.message : 'Could not load records'); setRecords([])
    })
  }, [domainId])
  useEffect(load, [load])

  async function add() {
    if (!draft.content.trim()) { setError('Enter a value'); return }
    setBusy(true); setError(null)
    try {
      await cappeApi.post(`/domains/${domainId}/dns`, {
        type: draft.type,
        name: draft.name.trim(),
        content: draft.content.trim(),
        ttl: Math.max(600, parseInt(draft.ttl, 10) || 600),
        prio: draft.type === 'MX' ? parseInt(draft.prio, 10) || 0 : null,
      })
      setDraft(EMPTY); load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add record')
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: string) {
    setError(null)
    try {
      await cappeApi.delete(`/domains/${domainId}/dns/${id}`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete record')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-50">DNS records</h2>
            <p className="mt-0.5 text-sm text-zinc-400">{domain}</p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
        </div>

        <div className="mb-3 flex flex-wrap items-end gap-2 rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
          <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })} className={input}>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="host (blank = root)"
            className={`w-32 ${input}`}
          />
          <input
            value={draft.content}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
            placeholder="value"
            className={`flex-1 ${input}`}
          />
          {draft.type === 'MX' && (
            <input
              value={draft.prio}
              onChange={(e) => setDraft({ ...draft, prio: e.target.value })}
              placeholder="prio"
              type="number"
              className={`w-16 ${input}`}
            />
          )}
          <input
            value={draft.ttl}
            onChange={(e) => setDraft({ ...draft, ttl: e.target.value })}
            type="number"
            className={`w-20 ${input}`}
          />
          <button
            onClick={add}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add
          </button>
        </div>
        {error && <p className="mb-2 text-sm text-red-400">{error}</p>}

        {records === null ? (
          <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
        ) : records.length === 0 ? (
          <p className="text-sm text-zinc-500">No records yet.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="py-1 pr-2">Type</th>
                <th className="py-1 pr-2">Host</th>
                <th className="py-1 pr-2">Value</th>
                <th className="py-1 pr-2">TTL</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-t border-zinc-800">
                  <td className="py-1.5 pr-2 font-medium text-zinc-300">{r.type}</td>
                  <td className="py-1.5 pr-2 text-zinc-400">{r.name || '@'}</td>
                  <td className="max-w-xs break-all py-1.5 pr-2 text-zinc-300">
                    {r.prio ? `${r.prio} ` : ''}{r.content}
                  </td>
                  <td className="py-1.5 pr-2 text-zinc-500">{r.ttl}</td>
                  <td className="py-1.5 text-right">
                    <button onClick={() => remove(r.id)} className="text-zinc-500 hover:text-red-400">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
