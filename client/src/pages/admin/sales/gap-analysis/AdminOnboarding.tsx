/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminButton, AdminInput, AdminTable } from '../../../../components/admin/AdminUI'
/**
 * Master-admin gap-analysis index page.
 *
 * Two entry points: a NEW company (the onboarding wizard at
 * `/admin/gap-analysis/:sessionId`) or an EXISTING company (employee-sync
 * enrichment run at `/admin/gap-analysis/company/:companyId`). Lists prior
 * sessions below.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Plus, Sparkles, Building2, Search, X } from 'lucide-react'

import { api } from '../../../../api/client'
import { adminOnboarding } from '../../../../api/admin/adminOnboarding'
import type {
  OnboardingSessionSummary,
  OnboardingStatus,
} from '../../../../api/admin/adminOnboarding'

const STATUS_FILTERS: { value: OnboardingStatus | 'all'; label: string }[] = [
  { value: 'in_progress', label: 'In progress' },
  { value: 'finalized', label: 'Finalized' },
  { value: 'abandoned', label: 'Abandoned' },
  { value: 'all', label: 'All' },
]

export default function AdminOnboarding({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<OnboardingSessionSummary[]>([])
  const [status, setStatus] = useState<OnboardingStatus | 'all'>('in_progress')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)

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
      navigate(`/admin/gap-analysis/${detail.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create session')
      setCreating(false)
    }
  }

  return (
    <div className={embedded ? '' : 'p-6'}>
      <div className="flex items-center justify-between mb-3">
        {embedded ? (
          <p className="text-xs text-zinc-500 max-w-xl">
            Take a <span className="text-zinc-300">new company</span> through the onboarding wizard,
            or resume an in-progress session below.
          </p>
        ) : (
          <div className="flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-emerald-400" />
            <h1 className="text-lg font-semibold text-zinc-100">Gap Analysis</h1>
          </div>
        )}
        <div className="flex items-center gap-2">
          <AdminButton
            onClick={() => setPickerOpen(true)}
            className="gap-2 h-9" variant="ghost"
          >
            <Building2 className="w-4 h-4" />
            Existing company
          </AdminButton>
          <AdminButton
            onClick={() => void startNew()}
            disabled={creating}
            className="gap-2 h-9 hover:opacity-90 disabled:opacity-50" variant="primary"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            New company
          </AdminButton>
        </div>
      </div>
      {!embedded && (
        <p className="text-xs text-zinc-500 mb-5">
          Run a gap analysis on a <span className="text-zinc-300">new company</span> (onboarding wizard)
          or sync an <span className="text-zinc-300">existing company's</span> employee roster to enrich
          its compliance &amp; jurisdictional coverage.
        </p>
      )}

      <div className="flex items-center gap-2 mb-4 text-xs">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setStatus(f.value)}
            className={`px-3 h-7 rounded-full border transition-colors ${
              status === f.value
                ? 'bg-zinc-100 text-zinc-900 border-zinc-100'
                : 'bg-transparent text-zinc-400 border-vsc-border hover:border-zinc-500'
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
        <div className="rounded-md border border-vsc-border bg-vsc-panel p-8 text-center text-sm text-zinc-400">
          No gap analyses yet. Start one for a <span className="text-zinc-100">New company</span> or
          an <span className="text-zinc-100">Existing company</span>.
        </div>
      ) : (
        <AdminTable>
          <thead className="bg-vsc-panel">
            <tr>
              <th className="text-left">Business</th>
              <th className="text-left">Industry</th>
              <th className="text-left">Step</th>
              <th className="text-left">Status</th>
              <th className="text-left">Updated</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr
                key={s.id}
                className="border-t border-vsc-border hover:bg-vsc-panel"
              >
                <td >
                  <Link
                    to={`/admin/gap-analysis/${s.id}`}
                    className="text-emerald-300 hover:underline"
                  >
                    {s.business_name || '(unnamed)'}
                  </Link>
                  {s.owner_email && (
                    <div className="text-[11px] text-zinc-500">
                      {s.owner_email}
                    </div>
                  )}
                  {s.status === 'finalized' && (
                    <Link
                      to={`/admin/gap-analysis/${s.id}/report`}
                      className="text-[11px] text-zinc-400 hover:text-emerald-300 hover:underline"
                    >
                      Gap analysis →
                    </Link>
                  )}
                </td>
                <td className="text-zinc-300">{s.industry || '—'}</td>
                <td className="text-zinc-300">{s.step}</td>
                <td >
                  <StatusPill status={s.status} />
                </td>
                <td className="text-zinc-500">
                  {new Date(s.updated_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </AdminTable>
      )}

      {pickerOpen && (
        <CompanyPicker
          onClose={() => setPickerOpen(false)}
          onPick={(id) => navigate(`/admin/gap-analysis/company/${id}`)}
        />
      )}
    </div>
  )
}

type PickerCompany = { id: string; company_name: string; signup_source?: string | null }

export function CompanyPicker({ onClose, onPick }: { onClose: () => void; onPick: (id: string) => void }) {
  const [companies, setCompanies] = useState<PickerCompany[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')

  useEffect(() => {
    api.get<{ registrations?: PickerCompany[] }>('/admin/business-registrations')
      .then((r) => setCompanies(r.registrations ?? []))
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = companies.filter((c) =>
    c.company_name.toLowerCase().includes(q.toLowerCase()),
  )

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-vsc-panel border border-vsc-border rounded-xl w-full max-w-lg max-h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-vsc-border">
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Pick a company</h3>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-3 border-b border-vsc-border">
          <div className="relative">
            <Search className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <AdminInput
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search companies…"
              className="border-vsc-border bg-vsc-bg pl-9 pr-3"
            />
          </div>
        </div>
        <div className="overflow-y-auto flex-1">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-zinc-500 p-4">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading companies…
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 p-4 text-center">No companies match.</p>
          ) : (
            filtered.map((c) => (
              <button
                key={c.id}
                onClick={() => onPick(c.id)}
                className="w-full text-left px-4 py-2.5 border-b border-vsc-border hover:bg-vsc-panel transition-colors flex items-center justify-between"
              >
                <span className="text-sm text-zinc-200">{c.company_name}</span>
                {c.signup_source && (
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{c.signup_source}</span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
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
