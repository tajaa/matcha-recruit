import { useState, useMemo } from 'react'
import { Select } from '../ui'
import { EmployeesTooltip } from './EmployeesTooltip'
import { useComplianceRequirements } from '../../hooks/compliance/useComplianceRequirements'
import type { ComplianceRequirement } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'
import type { CategoryGroup } from '../../generated/complianceCategories'
import { JURISDICTION_LEVEL_LABELS, RATE_TYPE_LABELS } from '../../api/compliance'
import type { ComplianceCheckMessage } from '../../hooks/compliance/useComplianceCheck'

const GROUP_OPTIONS = [
  { value: 'all', label: 'All Categories' },
  { value: 'labor', label: 'Core Labor' },
  { value: 'supplementary', label: 'Supplementary' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'oncology', label: 'Oncology' },
  { value: 'medical_compliance', label: 'Medical Compliance' },
]

type Props = {
  requirements: ComplianceRequirement[]
  loading: boolean
  onPin: (requirementId: string, isPinned: boolean) => void
  checkMessages: ComplianceCheckMessage[]
}

export function ComplianceRequirementsTab({ requirements, loading, onPin, checkMessages }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupFilter, setGroupFilter] = useState<'all' | CategoryGroup>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const filteredRequirements = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return requirements
    return requirements.filter((r) =>
      (r.title?.toLowerCase().includes(q)) ||
      (r.description?.toLowerCase().includes(q)) ||
      (r.current_value?.toLowerCase().includes(q)) ||
      (r.jurisdiction_name?.toLowerCase().includes(q)) ||
      (r.category?.toLowerCase().includes(q))
    )
  }, [requirements, searchQuery])

  const { sectionedCategories } = useComplianceRequirements(filteredRequirements)

  const filteredSections = useMemo(() => {
    if (groupFilter === 'all') return sectionedCategories
    return sectionedCategories.filter((s) => s.id === groupFilter)
  }, [sectionedCategories, groupFilter])

  // Detect missing coverage from check messages
  const missingCoverage = useMemo(() => {
    const cats = checkMessages.flatMap((m) => m.missing_categories ?? [])
    return new Set(cats.map((c) => c.trim().toLowerCase().replace(/[\s-]+/g, '_')))
  }, [checkMessages])

  function toggle(cat: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading requirements...</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search requirements..."
          className="flex-1 bg-zinc-800 border border-zinc-600 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-400 transition-colors"
        />
        <div className="w-48 shrink-0">
          <Select label="" options={GROUP_OPTIONS} value={groupFilter}
            onChange={(e) => setGroupFilter(e.target.value as 'all' | CategoryGroup)} />
        </div>
        <span className="text-xs text-zinc-500 shrink-0">
          {searchQuery ? `${filteredRequirements.length} of ${requirements.length}` : requirements.length} requirements
        </span>
      </div>

      {filteredSections.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-600">No requirements found. Run a compliance check to populate.</p>
        </div>
      ) : (
        filteredSections.map((section) => (
          <div key={section.id}>
            <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">
              {section.label} <span className="text-zinc-600 font-normal">({section.requirementCount})</span>
            </h3>
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              {section.categories.map(([cat, reqs]) => (
                <div key={cat} className="border-b border-zinc-800/60 last:border-0">
                  <button type="button" onClick={() => toggle(cat)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-zinc-900/30 transition-colors">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-medium text-zinc-200 uppercase tracking-wide">
                        {CATEGORY_LABELS[cat] || cat}
                      </span>
                      <span className="text-[11px] text-zinc-600">{reqs.length} active</span>
                      {missingCoverage.has(cat) && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/40">Missing Coverage</span>
                      )}
                    </div>
                    <span className="text-xs text-zinc-600">{expanded.has(cat) ? '−' : '+'}</span>
                  </button>
                  {expanded.has(cat) && (
                    <div className="divide-y divide-zinc-800/40">
                      {reqs.length === 0 ? (
                        <p className="px-4 py-4 text-xs text-zinc-600">
                          {missingCoverage.has(cat)
                            ? 'Coverage pending. Run a compliance check or admin refresh.'
                            : 'No active requirements detected yet.'}
                        </p>
                      ) : (
                        reqs.map((req) => (
                          <div key={req.id} className="px-4 py-3 hover:bg-zinc-900/20 transition-colors">
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-zinc-200">{req.title}</p>
                                <div className="flex flex-wrap items-center gap-2 mt-1">
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                                    {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                  </span>
                                  <span className="text-[11px] text-zinc-500">{req.jurisdiction_name}</span>
                                  {req.rate_type && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 border border-zinc-700">
                                      {RATE_TYPE_LABELS[req.rate_type] || req.rate_type}
                                    </span>
                                  )}
                                  {req.applicable_industries?.includes('healthcare') && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-900/20 text-cyan-400 border border-cyan-800/40">Medical</span>
                                  )}
                                  {(req.affected_employee_count ?? 0) > 0 && (
                                    <EmployeesTooltip names={req.affected_employee_names} count={req.affected_employee_count!}>
                                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/20 text-violet-400 border border-violet-800/40 cursor-default">
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
                                <span className="text-sm font-mono text-emerald-400 bg-emerald-900/20 border border-emerald-800/40 px-2.5 py-1 rounded shrink-0">
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
                                  <span className="text-[11px] text-zinc-600">Eff. {new Date(req.effective_date).toLocaleDateString()}</span>
                                )}
                                <button type="button" onClick={() => onPin(req.id, !req.is_pinned)}
                                  className={`text-[11px] transition-colors ${req.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-amber-400'}`}>
                                  {req.is_pinned ? 'Pinned' : 'Pin'}
                                </button>
                              </div>
                              {req.source_url && (
                                <a href={req.source_url} target="_blank" rel="noopener noreferrer"
                                  className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
                                  Source &rarr;
                                </a>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
