import { useEffect, useState } from 'react'
import { Button, Input, Modal } from './ui'
import { handbooks } from '../api/client'
import type { HandbookDistributionRecipient } from '../types/handbook'

type Props = {
  open: boolean
  onClose: () => void
  handbookId: string
  onDistributed?: () => void
}

export function HandbookDistributeModal({ open, onClose, handbookId, onDistributed }: Props) {
  const [mode, setMode] = useState<'all' | 'select'>('all')
  const [recipients, setRecipients] = useState<HandbookDistributionRecipient[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setResult(null)
    setMode('all')
    setSelected(new Set())
    setSearch('')
    setLoading(true)
    handbooks.listDistributionRecipients(handbookId)
      .then(setRecipients)
      .catch(() => setRecipients([]))
      .finally(() => setLoading(false))
  }, [open, handbookId])

  const alreadyAssigned = recipients.filter((r) => r.already_assigned).length
  const filtered = recipients.filter(
    (r) =>
      !r.already_assigned &&
      (r.name.toLowerCase().includes(search.toLowerCase()) ||
        r.email.toLowerCase().includes(search.toLowerCase())),
  )

  function toggleEmployee(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleSend() {
    setSending(true)
    try {
      const ids = mode === 'select' ? Array.from(selected) : undefined
      const res = await handbooks.distribute(handbookId, ids)
      setResult(`Distributed to ${res.assigned_count} employee(s). ${res.skipped_existing_count} already had it.`)
      onDistributed?.()
    } catch (err) {
      setResult(err instanceof Error ? err.message : 'Distribution failed')
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Distribute Handbook" width="md">
      {result ? (
        <div className="space-y-3">
          <p className="text-sm text-zinc-300">{result}</p>
          <Button size="sm" onClick={onClose}>Done</Button>
        </div>
      ) : loading ? (
        <p className="text-sm text-zinc-500">Loading recipients...</p>
      ) : (
        <div className="space-y-4">
          {alreadyAssigned > 0 && (
            <p className="text-xs text-zinc-500">{alreadyAssigned} employee(s) already assigned.</p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode('all')}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                mode === 'all'
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                  : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Send to all
            </button>
            <button
              type="button"
              onClick={() => setMode('select')}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                mode === 'select'
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                  : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Select employees
            </button>
          </div>

          {mode === 'select' && (
            <>
              <Input
                id="dist-search"
                label=""
                placeholder="Search employees..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <div className="max-h-56 overflow-y-auto border border-zinc-800 rounded-lg divide-y divide-zinc-800">
                {filtered.length === 0 ? (
                  <p className="px-3 py-4 text-xs text-zinc-600 text-center">No eligible employees found.</p>
                ) : (
                  filtered.map((r) => (
                    <label
                      key={r.employee_id}
                      className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-zinc-800/40"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(r.employee_id)}
                        onChange={() => toggleEmployee(r.employee_id)}
                        className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-zinc-200 truncate">{r.name}</p>
                        <p className="text-xs text-zinc-500 truncate">{r.email}</p>
                      </div>
                    </label>
                  ))
                )}
              </div>
              {selected.size > 0 && (
                <p className="text-xs text-zinc-400">{selected.size} selected</p>
              )}
            </>
          )}

          <Button
            size="sm"
            onClick={handleSend}
            disabled={sending || (mode === 'select' && selected.size === 0)}
          >
            {sending ? 'Sending...' : mode === 'all' ? 'Send to All Employees' : `Send to ${selected.size} Employee(s)`}
          </Button>
        </div>
      )}
    </Modal>
  )
}
