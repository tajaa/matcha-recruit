import { useState } from 'react'
import { FileDown, Sparkles, Loader2 } from 'lucide-react'
import { Card } from '../ui'
import { HelpHint } from './HelpHint'
import type { CoverageGap } from '../../types/broker'

/**
 * Carrier submission packet + AI coverage-gap — shared by the tenant and
 * off-platform client-detail surfaces. Caller passes the download + analyze fns.
 */
export function SubmissionPanel({ onDownload, onAnalyze }: {
  onDownload: () => Promise<unknown>
  onAnalyze: () => Promise<CoverageGap>
}) {
  const [downloading, setDownloading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [gap, setGap] = useState<CoverageGap | null>(null)

  const dl = async () => { setDownloading(true); try { await onDownload() } catch { /* surfaced by api */ } finally { setDownloading(false) } }
  const an = async () => { setAnalyzing(true); try { setGap(await onAnalyze()) } catch { setGap(null) } finally { setAnalyzing(false) } }

  return (
    <Card className="p-5">
      <div className="flex items-center gap-1.5 mb-1">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Carrier submission</h3>
        <HelpHint text="A carrier-ready underwriting packet built from this client's WC + EPL posture (the data already on file), plus an AI coverage-gap read of where they may be under-protected. The terms-winning artifact — take it to market at renewal." />
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Hand the PDF to carriers; use the coverage-gap to advise the client before renewal.</p>

      <div className="flex flex-wrap gap-2">
        <button onClick={dl} disabled={downloading}
          className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors disabled:opacity-50">
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Download submission PDF
        </button>
        <button onClick={an} disabled={analyzing}
          className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 px-3 py-1.5 rounded-lg hover:bg-white transition-colors disabled:opacity-50">
          {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Coverage-gap analysis
        </button>
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
