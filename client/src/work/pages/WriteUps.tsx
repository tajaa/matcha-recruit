import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Circle, FileSignature, Loader2, Plus } from 'lucide-react'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { listMyWriteUps, markWriteUpDelivered, uploadSignedCopy } from '../api/hrCases'
import type { ManagerCase } from '../types'
import WriteUpForm from '../components/panels/hr-cases/WriteUpForm'

function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export default function WriteUps() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { caseId } = useParams<{ caseId?: string }>()
  const [cases, setCases] = useState<ManagerCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const [revising, setRevising] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [deliveredOn, setDeliveredOn] = useState(today)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => listMyWriteUps().then(
    (res) => { setCases(res.cases); setError(null) },
    (err) => setError(err instanceof Error && err.message ? err.message : 'Could not load your write-ups'),
  ), [])
  useEffect(() => { void load() }, [load])

  const selected = cases?.find((c) => c.id === caseId) ?? null

  function submitted(result: { status: 'submitted' | 'held'; case: ManagerCase }) {
    setComposing(false)
    setRevising(false)
    setNotice(result.status === 'held'
      ? `${result.case.case_number}: HR needs to look at this one before it can go forward — they've been told.`
      : `${result.case.case_number}: sent to HR for review.`)
    void load()
    navigate(`${base}/write-ups/${result.case.id}`)
  }

  async function uploadSigned(c: ManagerCase, file: File) {
    setBusy(true)
    try {
      await uploadSignedCopy(c.id, file)
      setNotice(`${c.case_number}: signed copy filed. It's being checked now — you'll hear back if anything needs fixing.`)
      await load()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not upload the signed copy')
    } finally {
      setBusy(false)
    }
  }

  async function delivered(c: ManagerCase) {
    setBusy(true)
    try {
      await markWriteUpDelivered(c.id, deliveredOn)
      setNotice(`${c.case_number}: marked delivered. Upload the signed copy when you have it.`)
      await load()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not mark it delivered')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-5">
        <header className="flex items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold text-w-text"><FileSignature size={18} /> Write-ups</h1>
            <p className="text-xs text-w-faint">Write-ups you've sent to HR, and where each one stands.</p>
          </div>
          {!composing && (
            <button onClick={() => { setComposing(true); setNotice(null) }} className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi">
              <Plus size={14} /> New write-up
            </button>
          )}
        </header>

        {notice && <p role="status" className="rounded-lg border border-w-accent/30 bg-w-accent/10 px-3 py-2 text-sm text-w-text">{notice}</p>}
        {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
        {composing && <WriteUpForm onSubmitted={submitted} onCancel={() => setComposing(false)} />}

        {cases === null ? (
          <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-w-faint" /></div>
        ) : cases.length === 0 && !composing ? (
          <p className="rounded-xl border border-dashed border-w-line px-6 py-10 text-center text-sm text-w-dim">No write-ups yet.</p>
        ) : (
          <ul className="space-y-2">
            {cases.map((c) => (
              <li key={c.id} className={`rounded-xl border bg-w-surface ${c.id === caseId ? 'border-w-accent/60' : 'border-w-line'}`}>
                <button type="button" onClick={() => navigate(`${base}/write-ups/${c.id}`)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-w-text">{c.employee_name ?? 'Write-up'}{c.incident_number && <span className="text-w-faint"> · {c.incident_number}</span>}</p>
                    <p className="text-[11px] text-w-faint">{c.case_number}</p>
                  </div>
                  <span className="shrink-0 rounded-full bg-w-surface2 px-2 py-0.5 text-[11px] text-w-dim">{c.stage_label}</span>
                </button>

                {selected?.id === c.id && (
                  <div className="space-y-3 border-t border-w-line px-4 py-3 text-sm">
                    <ul className="space-y-1">
                      {c.checklist.map((item) => (
                        <li key={item.key} className="flex items-center gap-2 text-xs">
                          {item.done ? <CheckCircle2 size={13} className="text-emerald-400" /> : <Circle size={13} className="text-w-faint" />}
                          <span className={item.done ? 'text-w-text' : 'text-w-dim'}>{item.label}</span>
                        </li>
                      ))}
                    </ul>
                    {c.review?.held_for_hr && <p className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-200">{c.review.message}</p>}
                    {c.decision_reason && <p className="text-xs text-w-dim">HR asked: <span className="text-w-text">{c.decision_reason}</span></p>}
                    {c.review && c.review.notes.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-[11px] font-medium text-w-dim">Notes on your letter</p>
                        <ul className="list-disc space-y-0.5 pl-4 text-xs text-w-text">
                          {c.review.notes.map((n) => <li key={n.code}>{n.detail}</li>)}
                        </ul>
                      </div>
                    )}
                    {c.can_submit_draft && (revising
                      ? <WriteUpForm existing={c} onSubmitted={submitted} onCancel={() => setRevising(false)} />
                      : <button onClick={() => setRevising(true)} className="rounded-lg border border-w-line px-3 py-1.5 text-sm text-w-dim hover:text-w-text">{c.has_draft ? 'Send a revised draft' : 'Send the write-up'}</button>)}
                    {c.signed_check?.outcome === 'fix_needed' && (
                      <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                        <p className="font-medium">The signed copy needs another upload:</p>
                        <ul className="list-disc pl-4">{c.signed_check.problems.map((p) => <li key={p}>{p}</li>)}</ul>
                      </div>
                    )}
                    {c.signed_check?.outcome === 'with_hr' && <p className="text-xs text-w-dim">HR is reviewing the signed copy.</p>}
                    {c.signed_check?.outcome === 'verified' && <p className="text-xs text-emerald-300">Signed copy checked and filed.</p>}
                    {c.can_upload_signed && c.signed_check?.outcome !== 'with_hr' && (
                      <label className="block text-xs text-w-dim">
                        Upload the signed copy
                        <input
                          type="file"
                          accept=".pdf,.png,.jpg,.jpeg"
                          aria-label="Signed copy"
                          disabled={busy}
                          onChange={(e) => {
                            const file = e.target.files?.[0]
                            e.target.value = ''
                            if (file) void uploadSigned(c, file)
                          }}
                          className="mt-1 block text-sm"
                        />
                      </label>
                    )}
                    {c.can_mark_delivered && (
                      <div className="flex flex-wrap items-center gap-2">
                        <label htmlFor={`wu-delivered-${c.id}`} className="text-xs text-w-dim">Delivered on</label>
                        <input id={`wu-delivered-${c.id}`} type="date" max={today()} value={deliveredOn} onChange={(e) => setDeliveredOn(e.target.value)} className="rounded-md border border-w-line bg-w-surface2/60 px-2 py-1 text-sm text-w-text" />
                        <button disabled={busy} onClick={() => void delivered(c)} className="rounded-lg bg-w-accent px-3 py-1 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50">Mark delivered</button>
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
