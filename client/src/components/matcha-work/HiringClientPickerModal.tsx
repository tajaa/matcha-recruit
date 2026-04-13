import { useEffect, useState } from 'react'
import { X, Plus, Loader2, Building2, Search } from 'lucide-react'
import { listRecruitingClients, createRecruitingClient } from '../../api/matchaWork'
import type { RecruitingClient } from '../../types/matcha-work'

interface Props {
  onClose: () => void
  onPicked: (client: RecruitingClient | null) => void
  allowSkip?: boolean
}

const c = {
  bg: '#1e1e1e', cardBg: '#252526', border: '#333', text: '#d4d4d4',
  heading: '#e8e8e8', muted: '#8a8a8a', accent: '#60a5fa',
}

export default function HiringClientPickerModal({ onClose, onPicked, allowSkip = true }: Props) {
  const [clients, setClients] = useState<RecruitingClient[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newWebsite, setNewWebsite] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRecruitingClients()
      .then(setClients)
      .catch(() => setError('Failed to load hiring clients'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = search.trim()
    ? clients.filter((x) => x.name.toLowerCase().includes(search.toLowerCase()))
    : clients

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    setError(null)
    try {
      const created = await createRecruitingClient({ name, website: newWebsite.trim() || null })
      onPicked(created)
    } catch (e: unknown) {
      setError((e as Error)?.message || 'Failed to create hiring client')
      setCreating(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="relative my-8 w-full max-w-md rounded-xl border shadow-xl"
        style={{ background: c.cardBg, borderColor: c.border, color: c.text }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b p-4" style={{ borderColor: c.border }}>
          <div className="flex items-center gap-2">
            <Building2 size={16} style={{ color: c.accent }} />
            <h2 className="text-base font-semibold" style={{ color: c.heading }}>
              Who are you recruiting for?
            </h2>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-white/10" style={{ color: c.muted }}>
            <X size={16} />
          </button>
        </div>

        <div className="p-4">
          {!showCreate && (
            <>
              <div className="relative mb-3">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: c.muted }} />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search hiring clients..."
                  className="w-full rounded-lg border py-2 pl-9 pr-3 text-sm outline-none"
                  style={{ background: c.bg, borderColor: c.border, color: c.text }}
                />
              </div>

              {loading && (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="animate-spin" size={16} style={{ color: c.muted }} />
                </div>
              )}

              {!loading && filtered.length === 0 && (
                <p className="py-4 text-center text-sm" style={{ color: c.muted }}>
                  {clients.length === 0 ? 'No hiring clients yet' : 'No matches'}
                </p>
              )}

              {!loading && filtered.length > 0 && (
                <div className="max-h-64 space-y-1 overflow-y-auto">
                  {filtered.map((x) => (
                    <button
                      key={x.id}
                      onClick={() => onPicked(x)}
                      className="flex w-full items-center gap-3 rounded-lg border p-2 text-left transition-colors hover:bg-white/5"
                      style={{ borderColor: c.border }}
                    >
                      {x.logo_url ? (
                        <img src={x.logo_url} alt="" className="h-8 w-8 rounded object-cover" />
                      ) : (
                        <div
                          className="flex h-8 w-8 items-center justify-center rounded"
                          style={{ background: c.bg, color: c.muted }}
                        >
                          <Building2 size={14} />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium" style={{ color: c.heading }}>{x.name}</p>
                        {x.website && (
                          <p className="truncate text-xs" style={{ color: c.muted }}>{x.website}</p>
                        )}
                      </div>
                      {x.project_count != null && x.project_count > 0 && (
                        <span className="text-xs" style={{ color: c.muted }}>{x.project_count} active</span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              <button
                onClick={() => setShowCreate(true)}
                className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed py-2 text-sm transition-colors hover:bg-white/5"
                style={{ borderColor: c.border, color: c.accent }}
              >
                <Plus size={14} />
                New hiring client
              </button>

              {allowSkip && (
                <button
                  onClick={() => onPicked(null)}
                  className="mt-2 w-full rounded-lg py-2 text-xs transition-colors hover:bg-white/5"
                  style={{ color: c.muted }}
                >
                  Skip — not recruiting for a specific client
                </button>
              )}
            </>
          )}

          {showCreate && (
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide" style={{ color: c.muted }}>
                Client name
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Acme Corp"
                autoFocus
                className="mb-3 w-full rounded-lg border px-3 py-2 text-sm outline-none"
                style={{ background: c.bg, borderColor: c.border, color: c.text }}
              />
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide" style={{ color: c.muted }}>
                Website (optional)
              </label>
              <input
                type="text"
                value={newWebsite}
                onChange={(e) => setNewWebsite(e.target.value)}
                placeholder="acme.com"
                className="mb-3 w-full rounded-lg border px-3 py-2 text-sm outline-none"
                style={{ background: c.bg, borderColor: c.border, color: c.text }}
              />
              {error && <p className="mb-2 text-xs" style={{ color: '#ef4444' }}>{error}</p>}
              <div className="flex gap-2">
                <button
                  onClick={() => setShowCreate(false)}
                  disabled={creating}
                  className="flex-1 rounded-lg border py-2 text-sm disabled:opacity-50"
                  style={{ borderColor: c.border, color: c.text }}
                >
                  Back
                </button>
                <button
                  onClick={handleCreate}
                  disabled={!newName.trim() || creating}
                  className="flex-1 rounded-lg py-2 text-sm font-medium disabled:opacity-50"
                  style={{ background: c.accent, color: '#000' }}
                >
                  {creating ? <Loader2 className="mx-auto animate-spin" size={14} /> : 'Create'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
