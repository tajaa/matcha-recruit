import { useMemo } from 'react'
import { ExternalLink } from 'lucide-react'
import { LABEL } from '../../ui/typography'
import { HelpHint } from '../../ui/HelpHint'
import type { ComplianceRiskSummary, RiskIssue } from '../../../types/compliance'
import { money } from './helpers'

export function PostureCell({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="px-4 py-3">
      <p className={`${LABEL} flex items-center gap-1`}>
        {label}{hint && <HelpHint text={hint} />}
      </p>
      {children}
    </div>
  )
}

export function SevLine({ dot, n, word, active }: { dot: string; n: number; word: string; active: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs ${active ? 'text-zinc-200' : 'text-zinc-600'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${active ? dot : 'bg-zinc-700'}`} />
      <span className="font-mono tabular-nums font-semibold">{n}</span>
      <span>{word}</span>
    </div>
  )
}

export function ExposureFigure({ posture: p, issues }: { posture: ComplianceRiskSummary['posture']; issues: RiskIssue[] }) {
  const has = p.exposure_max_usd > 0
  // The authority behind the most DOLLARS — the signature detail that reads as a
  // legal instrument, not a to-do list.
  //
  // This used to take the first issue carrying any penalty, which is not the
  // same thing and read as a lie the moment the figures were grounded: a $500
  // wage issue sorted ahead of a $16,550 OSHA one, so the tile totalled $17,050
  // and captioned it "City of Los Angeles Office of Wage Standards" — naming the
  // authority behind 3% of it. Sum by authority and take the largest.
  const authority = useMemo(() => {
    const byAuthority = new Map<string, { usd: number; href: string | null }>()
    for (const i of issues) {
      const name = i.penalty?.enforcing_agency || i.statute_citation
      const usd = i.penalty?.civil_max ?? i.penalty?.civil_min
      if (!name || usd == null) continue
      const n = i.penalty?.per_violation && i.violation_count ? Math.max(1, i.violation_count) : 1
      const prev = byAuthority.get(name)
      byAuthority.set(name, {
        usd: (prev?.usd ?? 0) + usd * n,
        // Any grounded issue from this authority can vouch for it. The total is
        // a sum and has no single source, but the CAPTION names one authority —
        // and that authority's schedule is a real page.
        href: prev?.href ?? (i.penalty?.grounded ? i.penalty.source_url ?? null : null),
      })
    }
    let top: { name: string; href: string | null } | null = null
    let best = -1
    // Ties break on name so the caption doesn't flicker between equal authorities.
    for (const [name, v] of [...byAuthority].sort((a, b) => a[0].localeCompare(b[0]))) {
      if (v.usd > best) { best = v.usd; top = { name, href: v.href } }
    }
    return top
  }, [issues])

  if (!has) {
    return (
      <>
        <p className="font-mono text-lg font-medium text-zinc-400 mt-0.5">No quantified exposure</p>
        {p.exposure_unquantified_count > 0 && (
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {p.exposure_unquantified_count} issue{p.exposure_unquantified_count === 1 ? '' : 's'} carry penalties the statute doesn't quantify
          </p>
        )}
      </>
    )
  }
  return (
    <>
      {/* Sized to survive its own cell. At 2xl with spaces around the dash this
          needs ~245px to set "$16,650 – $17,050"; the cell is a quarter of the
          strip (~200px at a normal window), so the range broke across two lines
          and read as a rendering fault rather than a figure. */}
      {/* The dash needs air or it reads as a strikethrough through the figures,
          but not so much that the range wraps again — hence a margin rather
          than the spaces this had before. */}
      <p className="mt-0.5 whitespace-nowrap font-mono text-xl font-semibold leading-none tabular-nums text-zinc-100">
        {money(p.exposure_min_usd)}<span className="mx-1 font-normal text-zinc-600">–</span>{money(p.exposure_max_usd)}
      </p>
      {p.exposure_unquantified_count > 0 && (
        <p className="text-[11px] text-zinc-500 mt-1">+ {p.exposure_unquantified_count} unquantified</p>
      )}
      {/* The total is a SUM across authorities, so it carries no single link and
          stays plain. The caption names ONE authority though, and when that
          authority's figures were parsed from its own schedule, the caption goes
          to it. */}
      {authority && (
        <p className="text-[11px] font-mono text-zinc-500 mt-0.5 line-clamp-2">
          {authority.href ? (
            <a
              href={authority.href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-zinc-400 underline decoration-dotted decoration-zinc-700 underline-offset-2 hover:text-zinc-200 hover:decoration-zinc-500"
              title={`${authority.name} — opens the penalty schedule these figures were read from`}
            >
              {authority.name}
              <ExternalLink className="h-2.5 w-2.5 opacity-60" />
            </a>
          ) : (
            authority.name
          )}
        </p>
      )}
    </>
  )
}

export function EmployeesAffected({ posture: p, issues }: { posture: ComplianceRiskSummary['posture']; issues: RiskIssue[] }) {
  const names = useMemo(() => {
    const s = new Set<string>()
    issues.forEach((i) => i.employee_names.forEach((n) => s.add(n)))
    return [...s]
  }, [issues])
  return (
    <>
      <p className="font-mono text-2xl font-semibold tabular-nums text-zinc-100 mt-0.5" title={names.join(', ')}>
        {p.employees_affected}
      </p>
      {names.length > 0 && (
        <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{names.slice(0, 3).join(', ')}{names.length > 3 ? ` +${names.length - 3}` : ''}</p>
      )}
    </>
  )
}
