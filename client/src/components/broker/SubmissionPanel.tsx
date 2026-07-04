import { useState, useEffect } from 'react'
import { FileDown, Sparkles, Loader2, Plus, Trash2, Save, Check } from 'lucide-react'
import { Card } from '../ui'
import { HelpHint } from './HelpHint'
import type { CoverageGap, SubmissionNotes, SubmissionPreview } from '../../types/broker'

const EMPTY_NOTES: SubmissionNotes = { cover_note: '', annotations: [], updated_at: null }

/**
 * Carrier submission packet + AI coverage-gap — shared by the tenant and
 * off-platform client-detail surfaces. Lets the broker see a preview of what the
 * packet contains and attach commentary (a cover memo + labeled annotations
 * explaining scores / steps to improve) that leads the downloaded PDF. The
 * caller wires the tenant- vs external-specific API fns.
 */
export function SubmissionPanel({ onDownload, onAnalyze, loadPreview, loadNotes, saveNotes }: {
  onDownload: () => Promise<unknown>
  onAnalyze: () => Promise<CoverageGap>
  loadPreview: () => Promise<SubmissionPreview>
  loadNotes: () => Promise<SubmissionNotes>
  saveNotes: (n: SubmissionNotes) => Promise<SubmissionNotes>
}) {
  const [downloading, setDownloading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [gap, setGap] = useState<CoverageGap | null>(null)

  const [loading, setLoading] = useState(true)
  const [preview, setPreview] = useState<SubmissionPreview | null>(null)
  const [notes, setNotes] = useState<SubmissionNotes>(EMPTY_NOTES)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [savedTick, setSavedTick] = useState(false)

  // Load once on mount (panel is remounted each time the Submission tab opens).
  useEffect(() => {
    let alive = true
    setLoading(true)
    Promise.all([loadPreview().catch(() => null), loadNotes().catch(() => null)])
      .then(([p, n]) => {
        if (!alive) return
        setPreview(p)
        if (n) setNotes({ cover_note: n.cover_note ?? '', annotations: n.annotations ?? [], updated_at: n.updated_at ?? null })
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setCover = (v: string) => { setNotes((n) => ({ ...n, cover_note: v })); setDirty(true) }
  const addAnnotation = () => { setNotes((n) => ({ ...n, annotations: [...n.annotations, { label: '', note: '' }] })); setDirty(true) }
  const updateAnnotation = (i: number, field: 'label' | 'note', v: string) => {
    setNotes((n) => ({ ...n, annotations: n.annotations.map((a, j) => (j === i ? { ...a, [field]: v } : a)) }))
    setDirty(true)
  }
  const removeAnnotation = (i: number) => { setNotes((n) => ({ ...n, annotations: n.annotations.filter((_, j) => j !== i) })); setDirty(true) }

  const save = async () => {
    setSaving(true)
    try {
      const saved = await saveNotes(notes)
      setNotes({ cover_note: saved.cover_note ?? '', annotations: saved.annotations ?? [], updated_at: saved.updated_at ?? null })
      setDirty(false)
      setSavedTick(true)
      setTimeout(() => setSavedTick(false), 2000)
    } catch { /* surfaced by api */ } finally { setSaving(false) }
  }

  const dl = async () => { setDownloading(true); try { await onDownload() } catch { /* surfaced by api */ } finally { setDownloading(false) } }
  const an = async () => { setAnalyzing(true); try { setGap(await onAnalyze()) } catch { setGap(null) } finally { setAnalyzing(false) } }

  const num = (v: number | null | undefined) => (v === null || v === undefined ? '—' : String(v))
  const emr = preview?.wc.current_emr
  const stats: { label: string; value: string }[] = [
    { label: 'TRIR', value: num(preview?.wc.trir) },
    { label: 'DART', value: num(preview?.wc.dart_rate) },
    { label: 'Exp. mod', value: emr === null || emr === undefined ? '—' : emr.toFixed(2) },
    { label: 'EPL', value: preview?.epl.score !== null && preview?.epl.score !== undefined ? `${preview.epl.score}/100` : '—' },
    ...(preview?.readiness ? [{ label: 'Readiness', value: preview.readiness.score !== null && preview.readiness.score !== undefined ? `${preview.readiness.score}%` : '—' }] : []),
  ]

  return (
    <Card className="p-5">
      <div className="flex items-center gap-1.5 mb-1">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Carrier submission</h3>
        <HelpHint text="A carrier-ready underwriting packet built from this client's WC + EPL posture (the data already on file), plus an AI coverage-gap read of where they may be under-protected. The terms-winning artifact — take it to market at renewal." />
      </div>
      <p className="text-[11px] text-zinc-500 mb-4">Review what's in the packet, add your commentary, then hand the PDF to carriers.</p>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500 py-4">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading submission…
        </div>
      ) : (
        <>
          {/* Preview — what the packet will contain */}
          {preview && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 mb-4">
              <div className="text-[13px] text-zinc-200 font-medium">{preview.name || 'Client'}</div>
              <div className="text-[11px] text-zinc-500 mt-0.5">
                {[preview.industry, preview.headcount ? `${preview.headcount} employees` : null, preview.state].filter(Boolean).join(' · ') || '—'}
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {stats.map((s) => (
                  <div key={s.label} className="rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 min-w-[64px]">
                    <div className="text-[8px] uppercase tracking-wider text-zinc-500">{s.label}</div>
                    <div className="text-sm font-mono text-zinc-200 mt-0.5">{s.value}</div>
                  </div>
                ))}
              </div>
              {preview.sections.length > 0 && (
                <div className="mt-3">
                  <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Sections included</div>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.sections.map((s) => (
                      <span key={s} className="text-[11px] text-zinc-400 px-2 py-0.5 rounded-full border border-zinc-800 bg-zinc-900">{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Broker commentary editor */}
          <div className="mb-4">
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-[11px] uppercase tracking-wider text-zinc-400">Broker commentary</span>
              <HelpHint text="Your framing — a cover memo plus labeled annotations that explain specific scores or steps the client took to improve. This leads the submission PDF the carrier reads. Save before downloading." />
            </div>
            <textarea
              value={notes.cover_note}
              onChange={(e) => setCover(e.target.value)}
              placeholder="Cover memo — thoughts, context, and framing for the underwriter…"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors resize-y min-h-[72px]"
            />

            {notes.annotations.length > 0 && (
              <div className="mt-3 space-y-2">
                {notes.annotations.map((a, i) => (
                  <div key={i} className="flex gap-2 items-start">
                    <div className="flex-1 space-y-1.5">
                      <input
                        value={a.label}
                        onChange={(e) => updateAnnotation(i, 'label', e.target.value)}
                        placeholder="What this note is about (e.g. EPL Readiness 62/100)"
                        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-[13px] text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 transition-colors"
                      />
                      <textarea
                        value={a.note}
                        onChange={(e) => updateAnnotation(i, 'note', e.target.value)}
                        placeholder="Explain the score / steps taken to improve…"
                        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-[13px] text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 transition-colors resize-y min-h-[52px]"
                      />
                    </div>
                    <button
                      onClick={() => removeAnnotation(i)}
                      title="Remove annotation"
                      className="mt-1 p-1.5 rounded-md text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-3 mt-3">
              <button
                onClick={addAnnotation}
                className="inline-flex items-center gap-1.5 text-[13px] text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" /> Add annotation
              </button>
              <button
                onClick={save}
                disabled={saving || !dirty}
                className="inline-flex items-center gap-1.5 text-[13px] text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors disabled:opacity-40 disabled:hover:border-zinc-700"
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : savedTick ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Save className="h-3.5 w-3.5" />}
                {savedTick ? 'Saved' : 'Save commentary'}
              </button>
              {notes.updated_at && !dirty && !savedTick && (
                <span className="text-[11px] text-zinc-600">Last saved {new Date(notes.updated_at).toLocaleString()}</span>
              )}
            </div>
          </div>
        </>
      )}

      {/* Actions — always available; download re-fetches saved notes server-side */}
      <div className="flex flex-wrap gap-2 items-center">
            <button onClick={dl} disabled={downloading}
              className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors disabled:opacity-50">
              {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Download submission PDF
            </button>
            <button onClick={an} disabled={analyzing}
              className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 px-3 py-1.5 rounded-lg hover:bg-white transition-colors disabled:opacity-50">
              {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Coverage-gap analysis
            </button>
            {dirty && (
              <span className="text-[11px] text-amber-500/80">Save your commentary to include it in the PDF.</span>
            )}
      </div>

      {gap && (
        <div className="mt-4 space-y-3">
          {gap.available ? (
            <>
              {gap.summary && <p className="text-sm text-zinc-300">{gap.summary}</p>}
              {gap.gaps.length > 0 && (
                <div className="space-y-2">
                  {gap.gaps.map((g, i) => (
                    <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                      <div className="text-sm font-medium text-zinc-200">{g.line}</div>
                      <div className="text-xs text-zinc-400 mt-0.5">{g.concern}</div>
                      <div className="text-xs text-emerald-400 mt-1">→ {g.suggestion}</div>
                    </div>
                  ))}
                </div>
              )}
              {gap.actions.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">Pre-renewal actions</div>
                  <ul className="list-disc list-inside text-sm text-zinc-300 space-y-0.5">
                    {gap.actions.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}
              <p className="text-[10px] text-zinc-600">AI-generated{gap.model ? ` · ${gap.model}` : ''} — verify before sending to carriers.</p>
            </>
          ) : (
            <p className="text-sm text-zinc-500">Coverage-gap analysis is temporarily unavailable — try again shortly. (The submission PDF works regardless.)</p>
          )}
        </div>
      )}
    </Card>
  )
}
