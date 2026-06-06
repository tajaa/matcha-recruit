import { useEffect, useMemo, useState } from 'react'
import {
  UserCheck,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Upload,
  Bell,
  Check,
  X,
  Clock,
  AlertTriangle,
  Users,
  TrendingDown,
} from 'lucide-react'
import { StatCard } from '../../components/dashboard'
import TabHeader from '../../components/broker/action-center/TabHeader'
import { Button, Modal, Select, FileUpload, useToast } from '../../components/ui'
import {
  fetchBenefitEligibilityExceptions,
  nudgeEligibilityException,
  resolveEligibilityException,
  dismissEligibilityException,
  downloadBenefitRosterTemplate,
  uploadBenefitRoster,
  fetchBrokerClientsLite,
} from '../../api/broker'
import type {
  EligibilityException,
  EligibilityExceptionsSummary,
  BrokerReferredClient,
} from '../../types/broker'

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtMoney(n: number | null | undefined): string {
  if (n == null) return '$0'
  return `$${Math.round(n).toLocaleString()}`
}

const EMPTY_SUMMARY: EligibilityExceptionsSummary = {
  new_hire_count: 0,
  termination_leak_count: 0,
  total_open: 0,
  estimated_monthly_leak: 0,
}

// --- Upload roster modal ---

function UploadRosterModal({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean
  onClose: () => void
  onUploaded: () => void
}) {
  const { toast } = useToast()
  const [clients, setClients] = useState<BrokerReferredClient[]>([])
  const [companyId, setCompanyId] = useState('')
  const [loadingClients, setLoadingClients] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setLoadingClients(true)
    setError('')
    fetchBrokerClientsLite()
      .then((res) => setClients(res.clients))
      .catch(() => setError('Unable to load client list'))
      .finally(() => setLoadingClients(false))
  }, [open])

  async function handleDownloadTemplate() {
    try {
      await downloadBenefitRosterTemplate()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to download template')
    }
  }

  async function handleFiles(files: File[]) {
    const file = files[0]
    if (!file) return
    if (!companyId) {
      setError('Select a client company first')
      return
    }
    setUploading(true)
    setError('')
    try {
      await uploadBenefitRoster(companyId, file)
      toast('Roster uploaded', 'success')
      onUploaded()
      handleClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function handleClose() {
    setCompanyId('')
    setError('')
    onClose()
  }

  const options = clients.map((c) => ({ value: c.company_id, label: c.company_name }))

  return (
    <Modal open={open} onClose={handleClose} title="Upload Benefit Roster" width="md">
      <div className="space-y-4">
        <p className="text-sm text-zinc-400">
          Upload a benefit enrollment roster (CSV) for a client. We&apos;ll cross-reference it against
          new hires and terminations to surface enrollment gaps and premium leaks.
        </p>

        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1">Client Company</label>
          <Select
            options={options}
            value={companyId}
            placeholder={loadingClients ? 'Loading clients…' : 'Select a client…'}
            onChange={(e) => setCompanyId(e.target.value)}
            disabled={loadingClients || uploading}
          />
        </div>

        <FileUpload onFiles={handleFiles} accept=".csv" disabled={uploading || !companyId}>
          <p>
            {uploading ? (
              'Uploading…'
            ) : (
              <>
                Drop CSV here or <span className="text-emerald-400 underline">browse</span>
              </>
            )}
          </p>
        </FileUpload>

        <button
          type="button"
          onClick={handleDownloadTemplate}
          className="text-xs text-zinc-400 hover:text-emerald-400 transition-colors"
        >
          Download CSV template
        </button>

        {error && (
          <p className="text-sm text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</p>
        )}

        <div className="flex justify-end pt-2 border-t border-zinc-800">
          <Button variant="ghost" size="sm" onClick={handleClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// --- Action buttons shared by both card types ---

function ExceptionActions({
  ex,
  busy,
  onNudge,
  onResolve,
  onDismiss,
}: {
  ex: EligibilityException
  busy: boolean
  onNudge: () => void
  onResolve: () => void
  onDismiss: () => void
}) {
  const nudged = !!ex.last_nudge_sent_at
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Button size="sm" variant="secondary" disabled={busy || nudged} onClick={onNudge}>
        <Bell size={12} className="mr-1" />
        {nudged ? `Pinged ${fmtDate(ex.last_nudge_sent_at)}` : 'Ping Client HR'}
      </Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={onResolve}>
        <Check size={12} className="mr-1" />
        Resolve
      </Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={onDismiss}>
        <X size={12} className="mr-1" />
        Dismiss
      </Button>
    </div>
  )
}

// --- New-hire enrollment-gap card ---

function NewHireCard({
  ex,
  busy,
  onNudge,
  onResolve,
  onDismiss,
}: {
  ex: EligibilityException
  busy: boolean
  onNudge: () => void
  onResolve: () => void
  onDismiss: () => void
}) {
  const closed = ex.days_remaining != null && ex.days_remaining <= 0
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-100">{ex.employee_name}</p>
          <p className="text-xs text-zinc-500 mt-0.5">{ex.company_name}</p>
          <p className="text-xs text-zinc-500 mt-1 flex items-center gap-1">
            <Clock size={11} />
            Started {fmtDate(ex.reference_date)} · {ex.days_elapsed} days ago
          </p>
        </div>
        {closed ? (
          <span className="shrink-0 px-2.5 py-1 rounded-full bg-red-500/15 border border-red-500/30 text-red-300 text-[11px] font-semibold uppercase tracking-wide">
            Enrollment window CLOSED
          </span>
        ) : (
          <span className="shrink-0 px-2.5 py-1 rounded-full bg-red-500/15 border border-red-500/30 text-red-300 text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap">
            {ex.days_remaining} {ex.days_remaining === 1 ? 'Day' : 'Days'} Left to Enroll
          </span>
        )}
      </div>
      <div className="mt-3 pt-3 border-t border-zinc-800">
        <ExceptionActions
          ex={ex}
          busy={busy}
          onNudge={onNudge}
          onResolve={onResolve}
          onDismiss={onDismiss}
        />
      </div>
    </div>
  )
}

// --- Termination premium-leak banner ---

function TerminationBanner({
  ex,
  busy,
  onNudge,
  onResolve,
  onDismiss,
}: {
  ex: EligibilityException
  busy: boolean
  onNudge: () => void
  onResolve: () => void
  onDismiss: () => void
}) {
  return (
    <div className="rounded-xl border border-red-500/30 border-l-4 border-l-red-500 bg-red-500/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-red-300">
            Active Premium Leak Detected
          </p>
          <p className="text-sm text-zinc-200 mt-1">
            <span className="font-medium">{ex.company_name}</span>: {ex.employee_name} was terminated{' '}
            {ex.days_elapsed} days ago but still has active health deductions. Estimated leak:{' '}
            <span className="font-semibold text-red-300">{fmtMoney(ex.estimated_monthly_leak)}/mo</span>.
          </p>
          <div className="mt-3">
            <ExceptionActions
              ex={ex}
              busy={busy}
              onNudge={onNudge}
              onResolve={onResolve}
              onDismiss={onDismiss}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function BrokerEligibilityExceptions() {
  const { toast } = useToast()
  const [exceptions, setExceptions] = useState<EligibilityException[]>([])
  const [summary, setSummary] = useState<EligibilityExceptionsSummary>(EMPTY_SUMMARY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [showUpload, setShowUpload] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchBenefitEligibilityExceptions()
      setExceptions(res.exceptions)
      setSummary(res.summary)
    } catch {
      setError('Failed to load eligibility exceptions.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // Open items only, terminations (leaks) first, then new hires by fewest days remaining.
  const sorted = useMemo(() => {
    const open = exceptions.filter((e) => e.status === 'open')
    const rank = (e: EligibilityException) => (e.exception_type === 'termination_premium_leak' ? 0 : 1)
    return [...open].sort((a, b) => {
      const r = rank(a) - rank(b)
      if (r !== 0) return r
      const ad = a.days_remaining ?? Number.POSITIVE_INFINITY
      const bd = b.days_remaining ?? Number.POSITIVE_INFINITY
      return ad - bd
    })
  }, [exceptions])

  const onNudge = async (id: string) => {
    setBusyId(id)
    try {
      await nudgeEligibilityException(id)
      setExceptions((prev) =>
        prev.map((e) => (e.id === id ? { ...e, last_nudge_sent_at: new Date().toISOString() } : e)),
      )
      toast('Nudge sent', 'success')
    } catch {
      toast('Failed to send nudge', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const onResolve = async (id: string) => {
    setBusyId(id)
    try {
      await resolveEligibilityException(id)
      setExceptions((prev) => prev.map((e) => (e.id === id ? { ...e, status: 'resolved' } : e)))
      toast('Marked resolved', 'success')
    } catch {
      toast('Failed to resolve', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const onDismiss = async (id: string) => {
    setBusyId(id)
    try {
      await dismissEligibilityException(id)
      setExceptions((prev) => prev.map((e) => (e.id === id ? { ...e, status: 'dismissed' } : e)))
      toast('Dismissed', 'success')
    } catch {
      toast('Failed to dismiss', 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-4">
      <TabHeader
        icon={UserCheck}
        title="Eligibility Exceptions"
        hint="Open benefit-enrollment gaps and active premium leaks across your book — work the queue top to bottom."
        actions={
          <Button size="sm" variant="secondary" onClick={() => setShowUpload(true)}>
            <Upload size={14} className="mr-1" />
            Upload roster (CSV)
          </Button>
        }
      />

      {/* Summary stat row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Open Exceptions"
          value={summary.total_open}
          icon={AlertCircle}
          urgent={summary.total_open > 0}
        />
        <StatCard label="New-Hire Gaps" value={summary.new_hire_count} icon={Users} />
        <StatCard
          label="Premium Leaks"
          value={summary.termination_leak_count}
          icon={TrendingDown}
          urgent={summary.termination_leak_count > 0}
        />
        <StatCard
          label="Est. Monthly Leak"
          value={fmtMoney(summary.estimated_monthly_leak)}
          icon={AlertTriangle}
          urgent={summary.estimated_monthly_leak > 0}
        />
      </div>

      {/* Queue */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-zinc-500">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <AlertCircle className="h-8 w-8 mb-2 text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500 border border-zinc-800 rounded-xl border-dashed">
          <CheckCircle2 className="h-10 w-10 text-emerald-500/60 mb-3" />
          <p className="text-sm font-medium text-zinc-400">No open eligibility exceptions</p>
          <p className="text-xs mt-1">Every new hire is enrolled and no terminated employees are leaking premium.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {sorted.map((ex) =>
            ex.exception_type === 'termination_premium_leak' ? (
              <TerminationBanner
                key={ex.id}
                ex={ex}
                busy={busyId === ex.id}
                onNudge={() => onNudge(ex.id)}
                onResolve={() => onResolve(ex.id)}
                onDismiss={() => onDismiss(ex.id)}
              />
            ) : (
              <NewHireCard
                key={ex.id}
                ex={ex}
                busy={busyId === ex.id}
                onNudge={() => onNudge(ex.id)}
                onResolve={() => onResolve(ex.id)}
                onDismiss={() => onDismiss(ex.id)}
              />
            ),
          )}
        </div>
      )}

      <UploadRosterModal open={showUpload} onClose={() => setShowUpload(false)} onUploaded={load} />
    </div>
  )
}
