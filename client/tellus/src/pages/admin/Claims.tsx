import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Chip, ErrorText, Textarea } from '../../components/ui'
import type { AdminClaim } from '../../api/types'

const fmtDateTime = (iso: string) => new Date(iso).toLocaleString()

function toErrorMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback
}

export default function AdminClaims() {
  const [items, setItems] = useState<AdminClaim[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [note, setNote] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const res = await tellusApi.get<AdminClaim[]>('/admin/claims?status=pending')
      setItems(res)
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to load claims'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function approve(id: string) {
    setBusyId(id)
    setError('')
    try {
      await tellusApi.post(`/admin/claims/${id}/approve`)
      await load()
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to approve claim'))
    } finally {
      setBusyId(null)
    }
  }

  async function reject(id: string) {
    setBusyId(id)
    setError('')
    try {
      await tellusApi.post(`/admin/claims/${id}/reject`, { decision_note: note.trim() || null })
      setRejectingId(null)
      setNote('')
      await load()
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to reject claim'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-tu-border bg-tu-bg">
      <div className="flex items-center justify-between border-b border-tu-border px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-tu-text">
          <ShieldCheck className="h-4 w-4 text-tu-accent" /> Business claims
        </h1>
        <span className="text-xs text-tu-faint">{items.length} pending</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {error && <div className="px-4 pt-3"><ErrorText>{error}</ErrorText></div>}
        {loading && items.length === 0 && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}

        {items.map((c) => (
          <div key={c.id} className="border-b border-tu-border/70 px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-tu-text">{c.brand_name}</span>
                  <Chip>{c.brand_slug}</Chip>
                </div>
                <div className="mt-0.5 text-xs text-tu-faint">
                  {c.account_email}{c.account_display_name ? ` (${c.account_display_name})` : ''}
                  {c.claimant_ip ? ` · ${c.claimant_ip}` : ''} · filed {fmtDateTime(c.created_at)}
                </div>
                {c.note && <p className="mt-1 text-xs text-tu-dim">{c.note}</p>}
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" loading={busyId === c.id} onClick={() => void approve(c.id)}>Approve</Button>
                <Button
                  size="sm" variant="ghost"
                  onClick={() => setRejectingId(rejectingId === c.id ? null : c.id)}
                >
                  Reject
                </Button>
              </div>
            </div>

            {rejectingId === c.id && (
              <div className="mt-3 max-w-sm">
                <Textarea
                  label="Reason (visible to the claimant)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                />
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="soft" loading={busyId === c.id} onClick={() => void reject(c.id)}>
                    Confirm reject
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { setRejectingId(null); setNote('') }}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        ))}

        {!loading && items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-tu-faint">No pending claims.</p>
        )}
      </div>
    </div>
  )
}
