import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, HelpCircle, Loader2, Lock, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import { useMe } from '../../../hooks/useMe'
import {
  deleteWorkPermission,
  listWorkPermissions,
  setWorkPermission,
  type WorkAccessLevel,
  type WorkPermissionRosterEntry,
} from '../../api/workPermissions'
import AccessLevelPicker from './AccessLevelPicker'
import PermissionOnboardingWizard, { WORK_ACCESS_WIZARD_DISMISSED_KEY } from './PermissionOnboardingWizard'
import { ACCESS_LEVEL_COPY, canManageWorkPermissions, sourceLabel } from '../../utils/workAccess'

interface Props {
  onBackToConnections: () => void
}

function initials(entry: WorkPermissionRosterEntry): string {
  return (entry.name || entry.email).trim().charAt(0).toUpperCase()
}

function levelClass(level: WorkAccessLevel): string {
  if (level === 'admin') return 'bg-purple-500/15 text-purple-300 border-purple-400/30'
  if (level === 'operator') return 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
  if (level === 'reviewer') return 'bg-blue-500/15 text-blue-300 border-blue-400/30'
  if (level === 'member') return 'bg-amber-500/15 text-amber-300 border-amber-400/30'
  return 'bg-w-surface2 text-w-dim border-w-line'
}

export default function WorkspaceAccessPanel({ onBackToConnections }: Props) {
  const { me } = useMe()
  const canManage = canManageWorkPermissions(me?.work_access?.capabilities)
  const [entries, setEntries] = useState<WorkPermissionRosterEntry[]>([])
  const [companyId, setCompanyId] = useState<string>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draftLevel, setDraftLevel] = useState<Exclude<WorkAccessLevel, 'guest'>>('member')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [showWizard, setShowWizard] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await listWorkPermissions()
      setCompanyId(response.company_id)
      setEntries(response.permissions)
      if (canManage && response.permissions.every((entry) => !entry.explicit_level)) {
        try {
          if (!localStorage.getItem(WORK_ACCESS_WIZARD_DISMISSED_KEY)) setShowWizard(true)
        } catch { /* best effort */ }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load workspace access.')
    } finally {
      setLoading(false)
    }
  }, [canManage])

  useEffect(() => { void refresh() }, [refresh])

  const filteredEntries = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return entries
    return entries.filter((entry) => `${entry.name || ''} ${entry.email} ${entry.role}`.toLowerCase().includes(normalized))
  }, [entries, query])

  function beginEdit(entry: WorkPermissionRosterEntry) {
    setEditingId(entry.user_id)
    setDraftLevel(entry.effective_level === 'guest' ? 'member' : entry.effective_level)
  }

  async function save(entry: WorkPermissionRosterEntry) {
    setBusyId(entry.user_id)
    setError('')
    try {
      await setWorkPermission(entry.user_id, draftLevel, companyId)
      setEditingId(null)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update workspace access.')
    } finally {
      setBusyId(null)
    }
  }

  async function restoreDefault(entry: WorkPermissionRosterEntry) {
    setBusyId(entry.user_id)
    setError('')
    try {
      await deleteWorkPermission(entry.user_id, companyId)
      setEditingId(null)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not restore default access.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-w-surface">
      <div className="border-b border-w-line px-6 pb-5 pt-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <button type="button" onClick={onBackToConnections} className="mb-3 text-xs text-w-dim hover:text-w-text">← People</button>
            <div className="flex items-center gap-2">
              <ShieldCheck size={20} className="text-w-accent" />
              <h1 className="text-lg font-semibold text-w-text">Workspace access</h1>
            </div>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-w-dim">Control who can review sensitive work, approve proposals, and execute Huume actions. These settings apply to this company only.</p>
          </div>
          <button type="button" onClick={() => setShowWizard(true)} className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-3 py-2 text-xs font-medium text-w-text hover:border-w-accent/50 hover:bg-w-surface2">
            <HelpCircle size={14} /> How access works
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(['member', 'reviewer', 'operator', 'admin'] as const).map((level) => (
              <div key={level} className="rounded-xl border border-w-line bg-w-surface2/35 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-w-faint">{ACCESS_LEVEL_COPY[level].label}</p>
                <p className="mt-1 text-sm font-medium text-w-text">{ACCESS_LEVEL_COPY[level].short}</p>
                <p className="mt-1 text-xs leading-5 text-w-dim">{ACCESS_LEVEL_COPY[level].description}</p>
              </div>
            ))}
          </div>

          {!canManage && me?.work_access && (
            <div className="flex gap-3 rounded-xl border border-w-line bg-w-surface2/30 p-4">
              <Lock size={17} className="mt-0.5 shrink-0 text-w-dim" />
              <div><p className="text-sm font-medium text-w-text">Your access: {ACCESS_LEVEL_COPY[me.work_access.level].label}</p><p className="mt-1 text-xs leading-5 text-w-dim">Only a workspace admin can change access levels. You can review what your current level allows.</p></div>
            </div>
          )}

          {error && <div className="rounded-lg border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 className="text-sm font-semibold text-w-text">People with workspace access</h2><p className="mt-1 text-xs text-w-dim">Defaults are shown even when no custom grant exists.</p></div>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter people…" className="w-full rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text outline-none placeholder:text-w-faint focus:border-w-accent sm:w-64" />
          </div>

          {loading ? <div className="flex items-center gap-2 py-10 text-sm text-w-dim"><Loader2 size={16} className="animate-spin" /> Loading workspace access…</div> : filteredEntries.length === 0 ? <div className="rounded-xl border border-dashed border-w-line p-10 text-center text-sm text-w-dim">No eligible people found.</div> : (
            <div className="overflow-hidden rounded-xl border border-w-line">
              {filteredEntries.map((entry) => {
                const editing = editingId === entry.user_id
                const busy = busyId === entry.user_id
                return (
                  <div key={entry.user_id} className="border-b border-w-line last:border-b-0">
                    <div className="flex flex-wrap items-center gap-3 px-4 py-3.5">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-w-surface2 text-sm font-medium text-w-dim">{initials(entry)}</div>
                      <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-w-text">{entry.name || entry.email}</p><p className="truncate text-xs text-w-dim">{entry.email} · {entry.role}</p></div>
                      <div className="text-right"><span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-medium ${levelClass(entry.effective_level)}`}>{ACCESS_LEVEL_COPY[entry.effective_level].label}</span><p className="mt-1 text-[10px] text-w-faint">{sourceLabel(entry.effective_source)}</p></div>
                      {canManage && !entry.immutable && <button type="button" onClick={() => beginEdit(entry)} className="rounded-lg border border-w-line px-3 py-2 text-xs font-medium text-w-text hover:border-w-accent/50 hover:bg-w-surface2">Change</button>}
                      {entry.immutable && <span className="inline-flex items-center gap-1 text-[11px] text-w-faint"><Lock size={12} /> System</span>}
                    </div>
                    {editing && <div className="border-t border-w-line bg-w-surface2/20 px-4 py-4"><AccessLevelPicker value={draftLevel} onChange={setDraftLevel} disabled={busy} /><div className="mt-3 flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-w-dim">This grants authority only in this company.</p><div className="flex gap-2"><button type="button" onClick={() => void restoreDefault(entry)} disabled={busy || !entry.explicit_level} className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-3 py-2 text-xs text-w-dim hover:bg-w-surface2 disabled:cursor-not-allowed disabled:opacity-40"><RotateCcw size={13} /> Restore default</button><button type="button" onClick={() => void save(entry)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-2 text-xs font-medium text-white hover:bg-w-accent-hi disabled:opacity-50">{busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save access</button></div></div></div>}
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-500/5 p-4 text-xs leading-5 text-w-dim"><AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-300" /><p>Keep Operator access limited to people you trust to execute confirmed Huume actions. A Member can prepare a proposal, but an Operator is required to run it.</p></div>
        </div>
      </div>

      {showWizard && <PermissionOnboardingWizard onClose={() => setShowWizard(false)} onReview={() => setShowWizard(false)} />}
    </div>
  )
}
