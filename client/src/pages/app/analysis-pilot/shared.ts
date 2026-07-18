import type { AnalysisSession, DemoDatasetKey } from '../../../api/analysis-pilot/analysisPilot'

// A highlighted record attached to the next chat turn.
export type FocusChip = { cid: string; label: string }

// Mirror of the server's analysis_packs.base.slug() — needed only to mint
// `figure:` cids for extraction rows (metric records carry their cid already).
export const slugify = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'x'

// Each example is backed by a real bundled sample dataset (server-shipped CSV,
// not user data) — clicking one loads it for real into a dedicated demo session
// and asks the question for real, so it shows an actual computed-and-cited
// answer instead of a mockup.
export type AnalysisExample = { key: DemoDatasetKey; label: string; shape: string; question: string }

export const ANALYSIS_EXAMPLES: AnalysisExample[] = [
  { key: 'volatility', label: 'Fund prices', shape: '3 asset price series · 104 weeks',
    question: 'How volatile is this data, and has that changed recently?' },
  { key: 'financial', label: 'Quarterly financials', shape: 'Full P&L + balance sheet · 12 quarters',
    question: "What's the trend, and is it real or just noise?" },
  { key: 'insurance', label: 'GL loss run', shape: '6 policy years',
    question: "What's driving the loss ratio — frequency or severity?" },
  { key: 'inventory', label: 'Inventory ops', shape: '24 months',
    question: 'Where are we at risk of stockouts, and why?' },
]

// --------------------------------------------------------------------------- //
// Citation rendering — the model's replies carry corpus ids (metric:/ratio:/
// corr:/series:/figure:/compare:/dataset:) inline. Render them as clean chips
// (label = the record's human ref, tooltip = its summary) instead of raw UUIDs,
// and render the prose as markdown so bold/lists/tables show properly.
// --------------------------------------------------------------------------- //

export type CidInfo = { ref: string; summary: string }

/** cid → {ref, summary} across every computed record in the session (dataset
 *  metrics + saved comparisons), so a cited id resolves to a readable label. */
export function buildCidIndex(session: AnalysisSession): Map<string, CidInfo> {
  const idx = new Map<string, CidInfo>()
  const add = (recs?: Array<{ cid: string; ref: string; summary: string }>) => {
    for (const r of recs ?? []) idx.set(r.cid, { ref: r.ref, summary: r.summary })
  }
  for (const d of session.datasets ?? []) for (const b of Object.values(d.metrics ?? {})) add(b.records)
  for (const c of session.comparisons ?? []) add(c.result?.records)
  return idx
}

// 7 corpus prefixes; UUID + slug segments are [a-z0-9_-] (corr: joins two slugs
// with __, both metric: shapes resolve by exact lookup). Brackets optional.
export const CID_TOKEN_RE = /\[?((?:dataset|figure|series|metric|ratio|corr|compare):[a-z0-9][a-z0-9_-]*(?::[a-z0-9_-]+)*)\]?/gi

export function cidFallbackLabel(cid: string): string {
  const parts = cid.split(':')
  const last = parts[parts.length - 1] || cid
  return last.replace(/__/g, ' / ').replace(/[-_]+/g, ' ').trim() || 'cited'
}

/** Rewrite each inline cid token into a markdown link `[label](#cid:<cid>)` so
 *  the markdown renderer can turn it into a chip via the `a` component. */
export function linkifyCids(text: string, idx: Map<string, CidInfo>): string {
  return text.replace(CID_TOKEN_RE, (_full, cid: string) => {
    const label = (idx.get(cid)?.ref || cidFallbackLabel(cid)).replace(/[[\]()]/g, '').trim()
    return `[${label || 'cited'}](#cid:${cid})`
  })
}
