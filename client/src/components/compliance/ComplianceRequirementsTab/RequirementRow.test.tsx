import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { RequirementRow } from './RequirementRow'
import type { ComplianceRequirement } from '../../../types/compliance'
import type { Authority } from '../../../hooks/compliance/useComplianceRequirements'

function requirement(overrides: Partial<ComplianceRequirement> = {}): ComplianceRequirement {
  return {
    id: 'req-1',
    category: 'workplace_safety',
    rate_type: null,
    applicable_industries: [],
    jurisdiction_level: 'state',
    jurisdiction_name: 'California',
    title: 'Workplace Violence Prevention Plan',
    description: null,
    current_value: null,
    numeric_value: null,
    source_url: null,
    jurisdiction_requirement_id: 'cat-1',
    source_name: null,
    effective_date: null,
    previous_value: null,
    last_changed_at: null,
    affected_employee_count: null,
    affected_employee_names: [],
    min_wage_violation_count: null,
    is_pinned: false,
    has_components: false,
    ...overrides,
  }
}

const knownAuthorities: Map<string, Authority> = new Map()

describe('RequirementRow', () => {
  it('renders "Audit →" and calls onOpenAudit with the catalog id when has_components', async () => {
    const onOpenAudit = vi.fn()
    const user = userEvent.setup()
    render(
      <RequirementRow
        req={requirement({ has_components: true })}
        knownAuthorities={knownAuthorities}
        highlightId={null}
        onPin={vi.fn()}
        onOpenAudit={onOpenAudit}
      />
    )

    const link = screen.getByText('Audit →')
    expect(link).toBeInTheDocument()
    await user.click(link)
    expect(onOpenAudit).toHaveBeenCalledWith('cat-1')
  })

  it('renders no chevron and no inline checklist for a decomposed requirement', () => {
    render(
      <RequirementRow
        req={requirement({ has_components: true })}
        knownAuthorities={knownAuthorities}
        highlightId={null}
        onPin={vi.fn()}
        onOpenAudit={vi.fn()}
      />
    )

    // No expand/collapse affordance and no checklist content in this row —
    // the per-clause checklist lives only on the Audit tab now.
    expect(screen.queryByLabelText('Expand checklist')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Collapse checklist')).not.toBeInTheDocument()
    expect(screen.queryByText('No evidence on file')).not.toBeInTheDocument()
  })

  it('renders neither the link nor a checklist when has_components is false', () => {
    render(
      <RequirementRow
        req={requirement({ has_components: false })}
        knownAuthorities={knownAuthorities}
        highlightId={null}
        onPin={vi.fn()}
        onOpenAudit={vi.fn()}
      />
    )

    expect(screen.queryByText('Audit →')).not.toBeInTheDocument()
  })

  it('renders no link when onOpenAudit is absent, even if has_components is true', () => {
    render(
      <RequirementRow
        req={requirement({ has_components: true })}
        knownAuthorities={knownAuthorities}
        highlightId={null}
        onPin={vi.fn()}
      />
    )

    expect(screen.queryByText('Audit →')).not.toBeInTheDocument()
  })
})
