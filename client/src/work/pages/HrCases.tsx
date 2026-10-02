import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BookOpen, Briefcase, Loader2, X } from 'lucide-react'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import {
  acknowledgeHrCase, decideHrCase, dismissHrCase, getHrCase, getHrCaseReadiness, getSignedCopyUrl, getWriteUpDraftUrl, listHrCases,
  markWriteUpDelivered, recheckHrCase, uploadSignedCopy,
} from '../api/hrCases'
import { markHrCaseNotificationsRead } from '../api/notifications'
import type { MWNotification } from '../api/notifications'
import { useHrCaseUpdates } from '../hooks/useHrCaseUpdates'
import type { HrCase, HrCaseColumn, HrCaseReadiness } from '../types'
import HrCaseDetail from '../components/panels/hr-cases/HrCaseDetail'
import HrCaseUpdates from '../components/panels/hr-cases/HrCaseUpdates'
import HrCaseWizard, { HR_CASES_GUIDE_SEEN_KEY } from '../components/panels/hr-cases/HrCaseWizard'
import SetupCheck from '../components/panels/hr-cases/SetupCheck'
import { COLUMN_GUIDE, triggers } from '../components/panels/hr-cases/hrCaseGuide'

const STAGE_TONE: Partial<Record<HrCase['stage'], string>> = {
  flagged: 'bg-amber-500/15 text-amber-300',
  needs_attention: 'bg-red-500/15 text-red-300',
  changes_requested: 'bg-amber-500/15 text-amber-300',
  approved: 'bg-emerald-500/15 text-emerald-300',
  closed: 'bg-w-surface2 text-w-dim',
  dismissed: 'bg-w-surface2 text-w-faint',
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

const LIST_POLL_MS = 60_000

function guideSeen(): boolean {
  try { return localStorage.getItem(HR_CASES_GUIDE_SEEN_KEY) === '1' } catch { return true }
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`
}

export default function HrCases() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { caseId } = useParams<{ caseId?: string }>()
  const [columns, setColumns] = useState<HrCaseColumn[]>([])
  const [cases, setCases] = useState<HrCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<HrCase | null>(null)
  const [detailError, setDetailError] = useState<{ id: string; message: string } | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [guideDone, setGuideDone] = useState(guideSeen)
  const [readiness, setReadiness] = useState<HrCaseReadiness | null>(null)
  const [readinessState, setReadinessState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [fresh, setFresh] = useState<MWNotification | null>(null)

  const load = useCallback(() => listHrCases().then(
    (res) => { setColumns(res.columns); setCases(res.cases); setError(null) },
    (err) => setError(errorText(err, 'Could not load HR cases')),
  ), [])

  const loadDetail = useCallback((id: string) => getHrCase(id).then(
    (c) => { setDetail(c); setDetailError(null) },
    (err) => setDetailError({ id, message: errorText(err, 'Could not open that case') }),
  ), [])

  // A notice just landed: pull the board (and the open case) up to date and
  // say what happened, instead of waiting for the next poll.
  const latest = useRef({ load, loadDetail, caseId })
  useEffect(() => { latest.current = { load, loadDetail, caseId } })
  const updates = useHrCaseUpdates(useCallback((n: MWNotification) => {
    setFresh(n)
    void latest.current.load()
    if (latest.current.caseId) void latest.current.loadDetail(latest.current.caseId)
  }, []))

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const id = setInterval(() => { if (!document.hidden) void load() }, LIST_POLL_MS)
    return () => clearInterval(id)
  }, [load])
  useEffect(() => { if (caseId) void loadDetail(caseId) }, [caseId, loadDetail])

  // Opening a case is the signal that its notices were seen.
  const { reload: reloadUpdates } = updates
  useEffect(() => {
    if (caseId) void markHrCaseNotificationsRead(caseId).then(() => reloadUpdates(), () => {})
  }, [caseId, reloadUpdates])

  // First visit: walk them through it once the board has loaded.
  const empty = cases !== null && cases.length === 0
  const wizardOpen = helpOpen || (cases !== null && !guideDone)
  const wantsReadiness = wizardOpen || empty
  const readinessAsked = useRef(false)
  useEffect(() => {
    if (!wantsReadiness || readinessAsked.current) return
    readinessAsked.current = true
    setReadinessState('loading')
    getHrCaseReadiness().then(
      (r) => { setReadiness(r); setReadinessState('done') },
      () => setReadinessState('error'),
    )
  }, [wantsReadiness])
  const readinessLoading = readinessState === 'idle' || readinessState === 'loading'

  function closeWizard() {
    try { localStorage.setItem(HR_CASES_GUIDE_SEEN_KEY, '1') } catch { /* best effort */ }
    setHelpOpen(false)
    setGuideDone(true)
  }

  function openUpdate(n: MWNotification) {
    if (!n.is_read) updates.markRead(n.id)
    const target = typeof n.metadata?.hr_case_id === 'string' ? n.metadata.hr_case_id : null
    if (target && (n.link ?? '').includes('/hr-cases/')) navigate(`${base}/hr-cases/${target}`)
    else if (n.link) navigate(n.link)
  }

  const byColumn = useMemo(() => {
    const out: Record<string, HrCase[]> = {}
    for (const c of cases ?? []) (out[c.column] ??= []).push(c)
    return out
  }, [cases])

  const shown = caseId && detail?.id === caseId ? detail : null

  // Cases sitting in HR's hands right now.
  const waiting = useMemo(() => {
    const open = (stage: HrCase['stage']) => (cases ?? []).filter((c) => c.stage === stage)
    return [
      { key: 'hr_review', label: (n: number) => `${plural(n, 'write-up', 'write-ups')} to review`, items: open('hr_review') },
      { key: 'needs_attention', label: (n: number) => `${plural(n, 'signed copy', 'signed copies')} to look at`, items: open('needs_attention') },
    ].filter((w) => w.items.length > 0)
  }, [cases])

  async function refreshCase(id: string) {
    await Promise.all([load(), loadDetail(id)])
  }

  async function dismiss(reason: string) {
    if (!shown) return
    await dismissHrCase(shown.id, reason)
    await refreshCase(shown.id)
  }

  async function openDraft() {
    if (!shown) return
    const { url } = await getWriteUpDraftUrl(shown.id)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  async function decide(decision: 'approve' | 'request_changes', reason: string) {
    if (!shown) return
    await decideHrCase(shown.id, decision, reason)
    await refreshCase(shown.id)
  }

  async function openSigned() {
    if (!shown) return
    const { url } = await getSignedCopyUrl(shown.id)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  async function uploadSigned(file: File) {
    if (!shown) return
    await uploadSignedCopy(shown.id, file)
    await refreshCase(shown.id)
  }

  async function acknowledge() {
    if (!shown) return
    await acknowledgeHrCase(shown.id)
    await refreshCase(shown.id)
  }

  async function recheck() {
    if (!shown) return
    await recheckHrCase(shown.id)
    await refreshCase(shown.id)
  }

  async function delivered(deliveredOn: string) {
    if (!shown) return
    await markWriteUpDelivered(shown.id, deliveredOn)
    await refreshCase(shown.id)
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
      <div className="min-w-0 flex-1 overflow-auto">
        <div className="space-y-4 px-4 py-5">
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="flex items-center gap-2 text-lg font-semibold text-w-text"><Briefcase size={18} /> HR Cases</h1>
              <p className="text-xs text-w-faint">Incidents that may need a write-up, from first flag to signed copy.</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setHelpOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs text-w-dim transition-colors hover:bg-w-surface2 hover:text-w-text"
              >
                <BookOpen size={14} /> How it works
              </button>
              <HrCaseUpdates items={updates.items} unread={updates.unread} onOpen={openUpdate} onMarkAllRead={updates.markAllRead} />
            </div>
          </header>

          {fresh && (
            <div role="status" className="flex items-start gap-3 rounded-lg border border-w-accent/30 bg-w-accent/10 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-w-text">{fresh.title}</p>
                {fresh.body && <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-w-dim">{fresh.body}</p>}
              </div>
              <button type="button" onClick={() => { openUpdate(fresh); setFresh(null) }} className="shrink-0 text-xs font-medium text-w-accent hover:underline">Open</button>
              <button type="button" onClick={() => setFresh(null)} className="shrink-0 text-w-dim hover:text-w-text" aria-label="Dismiss"><X size={14} /></button>
            </div>
          )}

          {waiting.length > 0 && (
            <div className="flex flex-wrap items-center gap-2" aria-label="Waiting on you">
              <span className="text-[11px] font-medium uppercase tracking-wide text-amber-300">Waiting on you</span>
              {waiting.map((w) => (
                <button
                  key={w.key}
                  type="button"
                  onClick={() => navigate(`${base}/hr-cases/${w.items[0].id}`)}
                  className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200 transition-colors hover:bg-amber-500/20"
                >
                  {w.label(w.items.length)}
                </button>
              ))}
            </div>
          )}

          {empty && (
            <section aria-label="Nothing here yet" className="space-y-4 rounded-xl border border-w-line bg-w-surface px-4 py-4 sm:px-5">
              <div>
                <h2 className="text-sm font-semibold text-w-text">No cases yet, and that’s normal until something is flagged</h2>
                <p className="mt-1 text-xs leading-5 text-w-dim">Cases start on their own. You’ll get a bell and an email, and it will show up here.</p>
              </div>
              <ul className="grid gap-2 md:grid-cols-3">
                {triggers(readiness?.threshold).map((t) => (
                  <li key={t.title} className="rounded-lg border border-w-line bg-w-surface2/40 p-3">
                    <p className="text-xs font-medium text-w-text">{t.title}</p>
                    <p className="mt-1 text-[11px] leading-4 text-w-dim">{t.body}</p>
                  </li>
                ))}
              </ul>
              <SetupCheck readiness={readiness} loading={readinessLoading} error={readinessState === 'error'} />
              <button type="button" onClick={() => setHelpOpen(true)} className="inline-flex items-center gap-1.5 text-xs font-medium text-w-accent hover:underline">
                <BookOpen size={14} /> Walk me through it
              </button>
            </section>
          )}

          {error ? (
            <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error === 'Not found' ? "You don't have access to HR cases." : error}
            </p>
          ) : cases === null ? (
            <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-w-faint" /></div>
          ) : (
            <div className="grid auto-cols-[minmax(15rem,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2">
              {columns.map((col) => (
                <section key={col.key} aria-label={col.label} className="flex min-h-40 flex-col rounded-xl bg-w-surface2/40 p-2">
                  <h2 className="mb-2 flex items-center justify-between px-1 text-xs font-medium text-w-dim">
                    {col.label}
                    <span className="text-w-faint">{byColumn[col.key]?.length ?? 0}</span>
                  </h2>
                  {(byColumn[col.key] ?? []).length === 0 && COLUMN_GUIDE[col.key] && (
                    <p className="px-1 py-2 text-[11px] leading-4 text-w-faint">{COLUMN_GUIDE[col.key].empty}</p>
                  )}
                  <ul className="space-y-2">
                    {(byColumn[col.key] ?? []).map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          onClick={() => navigate(`${base}/hr-cases/${c.id}`)}
                          className={`w-full space-y-1 rounded-lg border bg-w-surface px-3 py-2 text-left transition-colors hover:bg-w-surface2 ${c.id === caseId ? 'border-w-accent/60' : 'border-w-line'}`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] text-w-faint">{c.case_number}</span>
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STAGE_TONE[c.stage] ?? 'bg-w-surface2 text-w-dim'}`}>
                              {c.stage_label}
                            </span>
                          </div>
                          <p className="truncate text-sm text-w-text">{c.incident_title ?? 'HR case'}</p>
                          <p className="truncate text-[11px] text-w-faint">
                            {[c.incident_number, c.employee_name].filter(Boolean).join(' · ') || 'No employee linked yet'}
                          </p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      {wizardOpen && (
        <HrCaseWizard
          columns={columns}
          readiness={readiness}
          readinessLoading={readinessLoading}
          readinessError={readinessState === 'error'}
          onClose={closeWizard}
        />
      )}

      {caseId && (
        shown ? (
          <HrCaseDetail hrCase={shown} onClose={() => navigate(`${base}/hr-cases`)} onDismiss={dismiss} onOpenDraft={openDraft} onDecide={decide} onDelivered={delivered}
            onOpenSigned={openSigned} onUploadSigned={uploadSigned} onAcknowledge={acknowledge} onRecheck={recheck} />
        ) : detailError?.id === caseId ? (
          <aside className="w-96 border-l border-w-line p-4 text-sm text-red-300" role="alert">{detailError.message}</aside>
        ) : (
          <aside className="flex w-96 items-center justify-center border-l border-w-line"><Loader2 size={16} className="animate-spin text-w-faint" /></aside>
        )
      )}
    </div>
  )
}
