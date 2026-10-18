import { AdminTable } from '../AdminUI'
import { Coffee } from 'lucide-react'
import type { AiUsageFeatureRollup, EspressoUsage } from '../../../types/aiUsage'
import { StatCard } from './StatCard'
import { ESPRESSO_FEATURE_PREFIX } from './constants'
import { fmtCost, fmtCount, fmtSeconds, fmtTokens, relTime } from './format'

const RUN_KIND_LABELS: Record<string, string> = {
  assistant: 'Assistant chat',
  agent_task: 'Tasks',
  job_search: 'Job search',
  card_agent: 'Agent cards',
  repo_question: 'Repo questions',
  task_draft: 'Task drafts',
}

function runKindLabel(kind: string): string {
  return RUN_KIND_LABELS[kind] ?? kind
}

function chipClass(active: boolean): string {
  return `text-[10px] px-1.5 py-0.5 rounded border ${
    active ? 'border-emerald-500 text-emerald-300' : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'
  }`
}

export function EspressoPanel({
  usage,
  features,
  loading,
  error,
  selectedFeature,
  onSelectFeature,
}: {
  usage: EspressoUsage | null
  features: AiUsageFeatureRollup[]
  loading: boolean
  error: string | null
  selectedFeature: string | null
  onSelectFeature: (feature: string) => void
}) {
  if (error) {
    return <p className="mb-4 text-xs text-red-400">Couldn't load Espresso usage: {error}</p>
  }
  if (!usage) {
    return loading ? <p className="mb-4 text-xs text-zinc-500">Loading Espresso usage…</p> : null
  }
  const { totals, spend, runs, tools } = usage
  if (totals.runs === 0 && spend.length === 0) return null

  return (
    <div className="mb-4">
      <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-zinc-500">
        <Coffee size={11} /> Espresso
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <StatCard label="Espresso spend" value={fmtCost(totals.cost_usd)} sub="models + searches" />
        <StatCard label="Runs" value={fmtCount(totals.runs)} sub={`${totals.people} people`} />
        <StatCard label="Model calls" value={fmtCount(totals.model_calls)} />
        <StatCard label="Web searches" value={fmtCount(totals.search_calls)} />
        <StatCard label="Tool calls" value={fmtCount(totals.tool_calls)} />
        <StatCard label="Failed runs" value={fmtCount(totals.failed)} />
      </div>

      {spend.length > 0 && (
        <div className="mt-2">
          <AdminTable>
            <thead>
              <tr className="text-left text-[11px] text-zinc-500 border-b border-zinc-800">
                <th >Spend by provider</th>
                <th className="text-right">Calls</th>
                <th className="text-right">Cost</th>
                <th className="text-right">In</th>
                <th className="text-right">Out</th>
                <th className="text-right">Failed</th>
              </tr>
            </thead>
            <tbody >
              {spend.map((r) => (
                <tr key={`${r.provider}/${r.model}`}>
                  <td className="font-mono text-zinc-200">
                    <span className="text-zinc-500">{r.provider} / </span>
                    {r.model}
                  </td>
                  <td className="text-right text-zinc-300">{fmtCount(r.calls)}</td>
                  <td className="text-right text-zinc-100">{fmtCost(r.cost_usd)}</td>
                  <td className="text-right text-zinc-400">{r.input_tokens ? fmtTokens(r.input_tokens) : '—'}</td>
                  <td className="text-right text-zinc-400">{r.output_tokens ? fmtTokens(r.output_tokens) : '—'}</td>
                  <td className={` text-right ${r.errors > 0 ? 'text-amber-400' : 'text-zinc-500'}`}>{r.errors}</td>
                </tr>
              ))}
            </tbody>
          </AdminTable>
        </div>
      )}

      {features.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {features.map((r) => (
            <button
              key={r.feature}
              type="button"
              onClick={() => onSelectFeature(r.feature)}
              className={chipClass(selectedFeature === r.feature)}
            >
              {r.feature.slice(ESPRESSO_FEATURE_PREFIX.length)} · {fmtCount(r.calls)} calls · {fmtCost(r.cost_usd)}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-2">
        <div className="rounded-lg border border-zinc-800 overflow-x-auto">
          <p className="px-3 pt-2 pb-1 text-[11px] font-semibold text-zinc-500">Runs by kind</p>
          {runs.length === 0 ? (
            <p className="p-4 text-center text-xs text-zinc-500">No runs in the selected window.</p>
          ) : (
            <AdminTable>
              <thead>
                <tr className="text-left text-[11px] text-zinc-500 border-b border-zinc-800">
                  <th >Kind</th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Failed</th>
                  <th className="text-right">People</th>
                  <th className="text-right">Model calls</th>
                  <th className="text-right">Searches</th>
                  <th className="text-right">Avg time</th>
                </tr>
              </thead>
              <tbody >
                {runs.map((r) => (
                  <tr key={r.kind}>
                    <td className="text-zinc-200">
                      {runKindLabel(r.kind)}
                      {r.live > 0 && <span className="ml-1.5 text-[10px] text-emerald-400">{r.live} live</span>}
                    </td>
                    <td className="text-right text-zinc-300">{fmtCount(r.runs)}</td>
                    <td className={` text-right ${r.failed > 0 ? 'text-amber-400' : 'text-zinc-500'}`}>{r.failed}</td>
                    <td className="text-right text-zinc-400">{r.people}</td>
                    <td className="text-right text-zinc-400">{fmtCount(r.model_calls)}</td>
                    <td className="text-right text-zinc-400">{fmtCount(r.search_calls)}</td>
                    <td className="text-right text-zinc-500">{fmtSeconds(r.avg_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </AdminTable>
          )}
        </div>

        <div className="rounded-lg border border-zinc-800 overflow-x-auto max-h-96 overflow-y-auto">
          <p className="px-3 pt-2 pb-1 text-[11px] font-semibold text-zinc-500">Tools used</p>
          {tools.length === 0 ? (
            <p className="p-4 text-center text-xs text-zinc-500">No tool calls in the selected window.</p>
          ) : (
            <AdminTable>
              <thead>
                <tr className="text-left text-[11px] text-zinc-500 border-b border-zinc-800">
                  <th >Tool</th>
                  <th className="text-right">Calls</th>
                  <th className="text-right">Failed</th>
                  <th className="text-right" title="Skipped by a budget, held for a yes, or outcome unknown">
                    Other
                  </th>
                  <th className="text-right">Runs</th>
                  <th className="text-right">Last used</th>
                </tr>
              </thead>
              <tbody >
                {tools.map((t) => {
                  const other = t.skipped + t.held + t.unknown
                  return (
                    <tr key={`${t.tool}/${t.kind}`}>
                      <td >
                        <span className="font-mono text-zinc-200">{t.tool}</span>
                        <span className="ml-1.5 text-[10px] text-zinc-600">
                          {t.kind}
                          {t.run_kinds.length > 0 && ` · ${t.run_kinds.map(runKindLabel).join(', ')}`}
                        </span>
                      </td>
                      <td className="text-right text-zinc-300">{fmtCount(t.calls)}</td>
                      <td className={` text-right ${t.errors > 0 ? 'text-amber-400' : 'text-zinc-500'}`}>{t.errors}</td>
                      <td
                        className="text-right text-zinc-500"
                        title={`${t.skipped} skipped · ${t.held} held · ${t.unknown} unknown`}
                      >
                        {other}
                      </td>
                      <td className="text-right text-zinc-400">{fmtCount(t.runs)}</td>
                      <td className="text-right text-zinc-500">
                        {t.last_used_at ? relTime(t.last_used_at) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </AdminTable>
          )}
        </div>
      </div>
    </div>
  )
}
