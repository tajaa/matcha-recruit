import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Briefcase, Loader2 } from 'lucide-react'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { decideHrCase, dismissHrCase, getHrCase, getWriteUpDraftUrl, listHrCases, markWriteUpDelivered } from '../api/hrCases'
import type { HrCase, HrCaseColumn } from '../types'
import HrCaseDetail from '../components/panels/hr-cases/HrCaseDetail'

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

export default function HrCases() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { caseId } = useParams<{ caseId?: string }>()
  const [columns, setColumns] = useState<HrCaseColumn[]>([])
  const [cases, setCases] = useState<HrCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<HrCase | null>(null)
  const [detailError, setDetailError] = useState<{ id: string; message: string } | null>(null)

  const load = useCallback(() => listHrCases().then(
    (res) => { setColumns(res.columns); setCases(res.cases); setError(null) },
    (err) => setError(errorText(err, 'Could not load HR cases')),
  ), [])

  const loadDetail = useCallback((id: string) => getHrCase(id).then(
    (c) => { setDetail(c); setDetailError(null) },
    (err) => setDetailError({ id, message: errorText(err, 'Could not open that case') }),
  ), [])

  useEffect(() => { void load() }, [load])
  useEffect(() => { if (caseId) void loadDetail(caseId) }, [caseId, loadDetail])

  const byColumn = useMemo(() => {
    const out: Record<string, HrCase[]> = {}
    for (const c of cases ?? []) (out[c.column] ??= []).push(c)
    return out
  }, [cases])

  const shown = caseId && detail?.id === caseId ? detail : null

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

  async function delivered(deliveredOn: string) {
    if (!shown) return
    await markWriteUpDelivered(shown.id, deliveredOn)
    await refreshCase(shown.id)
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="min-w-0 flex-1 overflow-auto">
        <div className="space-y-4 px-4 py-5">
          <header>
            <h1 className="flex items-center gap-2 text-lg font-semibold text-w-text"><Briefcase size={18} /> HR Cases</h1>
            <p className="text-xs text-w-faint">Incidents that may need a write-up, from first flag to signed copy.</p>
          </header>

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

      {caseId && (
        shown ? (
          <HrCaseDetail hrCase={shown} onClose={() => navigate(`${base}/hr-cases`)} onDismiss={dismiss} onOpenDraft={openDraft} onDecide={decide} onDelivered={delivered} />
        ) : detailError?.id === caseId ? (
          <aside className="w-96 border-l border-w-line p-4 text-sm text-red-300" role="alert">{detailError.message}</aside>
        ) : (
          <aside className="flex w-96 items-center justify-center border-l border-w-line"><Loader2 size={16} className="animate-spin text-w-faint" /></aside>
        )
      )}
    </div>
  )
}
