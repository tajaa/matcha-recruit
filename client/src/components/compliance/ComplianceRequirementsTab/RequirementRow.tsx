import { EmployeesTooltip } from '../EmployeesTooltip'
import { requirementAuthority } from '../../../hooks/compliance/useComplianceRequirements'
import type { Authority } from '../../../hooks/compliance/useComplianceRequirements'
import type { ComplianceRequirement } from '../../../types/compliance'
import { JURISDICTION_LEVEL_LABELS, RATE_TYPE_LABELS } from '../../../api/compliance/compliance'
import { isFuture } from './helpers'

type Props = {
  req: ComplianceRequirement
  knownAuthorities: Map<string, Authority>
  highlightId: string | null
  readOnly?: boolean
  onPin: (requirementId: string, isPinned: boolean) => void
}

export function RequirementRow({ req, knownAuthorities, highlightId, readOnly, onPin }: Props) {
  const authority = requirementAuthority(req, knownAuthorities)
  return (
    <div key={req.id} data-req-id={req.id}
      className={`px-4 py-3 transition-colors ${
        highlightId === req.id
          ? 'bg-emerald-500/[0.07] ring-1 ring-inset ring-emerald-500/40'
          : 'hover:bg-white/[0.02]'
      }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200">{req.title}</p>
          <div className="flex flex-wrap items-center gap-2 mt-1">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">
              {JURISDICTION_LEVEL_LABELS[authority.level] || authority.level}
            </span>
            <span className="text-[11px] text-zinc-500">{authority.name}</span>
            {req.rate_type && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-500 border border-white/[0.08]">
                {RATE_TYPE_LABELS[req.rate_type] || req.rate_type}
              </span>
            )}
            {req.applicable_industries?.includes('healthcare') && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">Medical</span>
            )}
            {(req.affected_employee_count ?? 0) > 0 && (
              <EmployeesTooltip names={req.affected_employee_names} count={req.affected_employee_count!}>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08] cursor-default">
                  {req.affected_employee_count} employee{req.affected_employee_count !== 1 ? 's' : ''}
                </span>
              </EmployeesTooltip>
            )}
            {(req.min_wage_violation_count ?? 0) > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/20 text-red-400 border border-red-800/40">
                {req.min_wage_violation_count} below threshold
              </span>
            )}
          </div>
        </div>
        {req.current_value && (
          <span className="text-sm font-mono text-zinc-200 bg-white/[0.06] border border-white/[0.08] px-2.5 py-1 rounded shrink-0">
            {req.current_value}
          </span>
        )}
      </div>
      {req.description && (
        <p className="text-xs text-zinc-500 mt-2 leading-relaxed">{req.description}</p>
      )}
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-3">
          {req.effective_date && (
            isFuture(req.effective_date) ? (
              // A catalog row can be current for us and not yet law:
              // the catalog deliberately stores forward-looking rules.
              // "Eff. 7/1/2027" reads as "in force since" — the exact
              // misread this avoids.
              <span
                className="text-[11px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/40"
                title="Not yet in force — no action required until this date">
                Takes effect {new Date(req.effective_date).toLocaleDateString()}
              </span>
            ) : (
              <span className="text-[11px] text-zinc-600">Eff. {new Date(req.effective_date).toLocaleDateString()}</span>
            )
          )}
          {req.statute_citation && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/20 text-emerald-400 border border-emerald-800/40"
              title={req.citation_verified_at ? `Verified ${new Date(req.citation_verified_at).toLocaleDateString()}` : undefined}>
              {req.statute_citation}
            </span>
          )}
          {req.jurisdictional_basis?.map((b) => (
            <span
              key={b.item_id}
              className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]"
              title={`This ${req.jurisdiction_level} requirement sits on top of the ${b.level} floor — it must meet or exceed ${b.citation}, which does not itself set this value.`}>
              {b.level} floor: {b.citation}
            </span>
          ))}
          {!readOnly && (
            <button type="button" onClick={() => onPin(req.id, !req.is_pinned)}
              className={`text-[11px] transition-colors ${req.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-amber-400'}`}>
              {req.is_pinned ? 'Pinned' : 'Pin'}
            </button>
          )}
        </div>
        {req.source_url && (
          <span className="flex items-center gap-1.5">
            {req.source_url_status === 'dead' && (
              <span
                className="rounded border border-red-500/30 bg-red-500/15 px-1 py-px text-[10px] text-red-400"
                title="This source link failed its last liveness check. The citation is kept so it can be re-verified once the authority fixes or moves the page.">
                link broken
              </span>
            )}
            <a href={req.source_url} target="_blank" rel="noopener noreferrer"
              className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
              Source &rarr;
            </a>
          </span>
        )}
      </div>
    </div>
  )
}
