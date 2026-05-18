/**
 * Master-admin onboarding wizard index page.
 *
 * Shows in-progress + finalized sessions and a "New Onboarding" CTA. The
 * wizard shell lives at `/admin/onboarding/:sessionId`.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Plus, Wand2 } from 'lucide-react'

import { adminOnboarding } from '../../api/adminOnboarding'
import type {
  OnboardingSessionSummary,
  OnboardingStatus,
} from '../../api/adminOnboarding'

const STATUS_FILTERS: { value: OnboardingStatus | 'all'; label: string }[] = [
  { value: 'in_progress', label: 'In progress' },
  { value: 'finalized', label: 'Finalized' },
  { value: 'abandoned', label: 'Abandoned' },
  { value: 'all', label: 'All' },
]

export default function AdminOnboarding() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<OnboardingSessionSummary[]>([])
  const [status, setStatus] = useState<OnboardingStatus | 'all'>('in_progress')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await adminOnboarding.listSessions(
        status === 'all' ? undefined : status,
      )
      setSessions(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function startNew() {
    if (creating) return
    setCreating(true)
    setError(null)
    try {
      const idem = crypto.randomUUID()
      const detail = await adminOnboarding.createSession(idem)
      navigate(`/admin/onboarding/${detail.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create session')
      setCreating(false)
    }
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <Wand2 className="w-5 h-5 text-emerald-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Onboarding wizard</h1>
        </div>
        <button
          onClick={() => void startNew()}
          disabled={creating}
          className="inline-flex items-center gap-2 px-4 h-9 rounded-md bg-emerald-500/90 hover:bg-emerald-500 text-zinc-950 text-sm font-medium disabled:opacity-50"
        >
          {creating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          New onboarding
        </button>
      </div>

      <div className="flex items-center gap-2 mb-4 text-xs">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setStatus(f.value)}
            className={`px-3 h-7 rounded-full border transition-colors ${
              status === f.value
                ? 'bg-zinc-100 text-zinc-900 border-zinc-100'
                : 'bg-transparent text-zinc-400 border-zinc-700 hover:border-zinc-500'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading sessions…
        </div>
      ) : sessions.length === 0 ? (
        <div className="rounded-md border border-zinc-800 bg-zinc-900/50 p-8 text-center text-sm text-zinc-400">
          No sessions yet. Click <span className="text-zinc-100">New onboarding</span> to start one.
        </div>
      ) : (
        <div className="rounded-md border border-zinc-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900/80 text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="text-left px-4 py-2">Business</th>
                <th className="text-left px-4 py-2">Industry</th>
                <th className="text-left px-4 py-2">Step</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.id}
                  className="border-t border-zinc-800 hover:bg-zinc-900/50"
                >
                  <td className="px-4 py-2">
                    <Link
                      to={`/admin/onboarding/${s.id}`}
                      className="text-emerald-300 hover:underline"
                    >
                      {s.business_name || '(unnamed)'}
                    </Link>
                    {s.owner_email && (
                      <div className="text-[11px] text-zinc-500">
                        {s.owner_email}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-zinc-300">{s.industry || '—'}</td>
                  <td className="px-4 py-2 text-zinc-300">{s.step}</td>
                  <td className="px-4 py-2">
                    <StatusPill status={s.status} />
                  </td>
                  <td className="px-4 py-2 text-zinc-500 text-xs">
                    {new Date(s.updated_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatusPill({ status }: { status: OnboardingStatus }) {
  const styles: Record<OnboardingStatus, string> = {
    in_progress: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    finalized: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    abandoned: 'bg-zinc-700/30 text-zinc-400 border-zinc-700',
  }
  return (
    <span
      className={`inline-flex items-center px-2 h-5 rounded-full text-[10.5px] uppercase tracking-wider border ${styles[status]}`}
    >
      {status.replace('_', ' ')}
    </span>
  )
}
