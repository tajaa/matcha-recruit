import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ComplianceAuditTab } from './ComplianceAuditTab'
import * as complianceApi from '../../api/compliance'
import type {
  ComplianceAuditOverview,
  ComplianceAuditStatute,
  RequirementComponentChecklist,
} from '../../types/compliance'

vi.mock('../../api/compliance', () => ({
  fetchComplianceAudit: vi.fn(),
  fetchRequirementComponents: vi.fn(),
  attestRequirementComponent: vi.fn(),
}))

// jsdom doesn't implement scrollIntoView. The target-focus effect's two
// setTimeouts are deliberately left un-cleaned-up (see ComplianceAuditTab's
// own comment), so the 60ms one can still fire during a later test's async
// waits — stub it so that doesn't throw.
Element.prototype.scrollIntoView = vi.fn()

function statute(overrides: Partial<ComplianceAuditStatute> = {}): ComplianceAuditStatute {
  return {
    jurisdiction_requirement_id: 'cat-1',
    title: 'Workplace Violence Prevention Plan',
    statute_citation: 'Cal. Lab. Code § 6401.9',
    category: 'workplace_safety',
    authority_level: 'state',
    authority_name: 'California',
    component_count: 5,
    locations: [
      {
        location_id: 'loc-fresno',
        location_label: 'Fresno',
        employee_count: 12,
        summary: {
          total: 5, known: 2, coverage_pct: 40, derived: 1, attested: 1,
          count_compliant: 1, count_non_compliant: 0, count_in_progress: 1, count_unknown: 3,
        },
      },
      {
        location_id: 'loc-la',
        location_label: 'Los Angeles',
        employee_count: 40,
        summary: {
          total: 5, known: 5, coverage_pct: 100, derived: 5, attested: 0,
          count_compliant: 5, count_non_compliant: 0, count_in_progress: 0, count_unknown: 0,
        },
      },
    ],
    summary: {
      total: 10, known: 7, coverage_pct: 70, derived: 6, attested: 1,
      count_compliant: 6, count_non_compliant: 0, count_in_progress: 1, count_unknown: 3,
    },
    exposure: { penalty: { civil_max: 25000, enforcing_agency: 'Cal/OSHA', grounded: true }, directional: true },
    ...overrides,
  }
}

// The coverage badge splits "known/total known" and "· pct%" across a nested
// <span> (deliberately, for the dimmer % color) — a plain getByText string
// won't match text split across sibling text nodes and a child element, so
// match on the containing element's full textContent instead.
function byExactText(text: string) {
  return (_content: string, element: Element | null) => element?.textContent === text
}

function overview(statutes: ComplianceAuditStatute[]): ComplianceAuditOverview {
  return {
    statutes,
    summary: statutes.length
      ? statutes.reduce((acc, s) => ({
          total: acc.total + s.summary.total, known: acc.known + s.summary.known,
          coverage_pct: null, derived: 0, attested: 0,
          count_compliant: 0, count_non_compliant: 0, count_in_progress: 0, count_unknown: 0,
        }), { total: 0, known: 0, coverage_pct: null, derived: 0, attested: 0, count_compliant: 0, count_non_compliant: 0, count_in_progress: 0, count_unknown: 0 })
      : { total: 0, known: 0, coverage_pct: null, derived: 0, attested: 0, count_compliant: 0, count_non_compliant: 0, count_in_progress: 0, count_unknown: 0 },
    location_count: new Set(statutes.flatMap((s) => s.locations.map((l) => l.location_id))).size,
  }
}

function checklist(overrides: Partial<RequirementComponentChecklist> = {}): RequirementComponentChecklist {
  return {
    jurisdiction_requirement_id: 'cat-1',
    location_id: 'loc-fresno',
    title: 'Workplace Violence Prevention Plan',
    statute_citation: 'Cal. Lab. Code § 6401.9',
    components: [
      {
        component_key: 'annual_training',
        label: 'Annual Training',
        question: 'All employees trained interactively < 12 months?',
        statute_citation: 'Cal. Lab. Code § 6401.9(b)',
        suggested_fix: 'Scope and assign an annual training program.',
        severity: 'critical',
        sort_order: 2,
        derivable: true,
        derivation_source: 'training_records',
        status: 'unknown',
        basis: null,
        evidence: {},
        attested_note: null,
        attested_at: null,
        derived_at: null,
      },
      {
        component_key: 'hazard_assessment',
        label: 'Hazard Assessment',
        question: 'Per-site assessment with workplace-specific hazards?',
        statute_citation: 'Cal. Lab. Code § 6401.9(b) (hazard identification)',
        suggested_fix: 'Schedule per-site hazard assessments.',
        severity: 'important',
        sort_order: 4,
        derivable: false,
        derivation_source: null,
        status: 'unknown',
        basis: null,
        evidence: {},
        attested_note: null,
        attested_at: null,
        derived_at: null,
      },
    ],
    summary: {
      total: 5, known: 0, coverage_pct: null, derived: 0, attested: 0,
      count_compliant: 0, count_non_compliant: 0, count_in_progress: 0, count_unknown: 5,
    },
    exposure: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(complianceApi.fetchComplianceAudit).mockReset()
  vi.mocked(complianceApi.fetchRequirementComponents).mockReset()
  vi.mocked(complianceApi.attestRequirementComponent).mockReset()
  // Every (location, catalog) pair used below — pre-seed "already seen" so
  // the audit-reveal modal never auto-opens and steals focus/timers (same
  // idiom as ComponentChecklist.test.tsx).
  localStorage.setItem('matcha_audit_reveal_seen:loc-fresno:cat-1', '1')
  localStorage.setItem('matcha_audit_reveal_seen:loc-la:cat-1', '1')
})

describe('ComplianceAuditTab', () => {
  it('groups by statute with a row per location', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText('Workplace Violence Prevention Plan')).toBeInTheDocument())
    expect(screen.getByText('Fresno')).toBeInTheDocument()
    expect(screen.getByText('Los Angeles')).toBeInTheDocument()
    expect(screen.getByText(byExactText('2/5 known · 40%'))).toBeInTheDocument()
    expect(screen.getByText(byExactText('5/5 known · 100%'))).toBeInTheDocument()
  })

  it('renders the empty state, not a blank panel', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([]))
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText(/No statute in your jurisdictions has a per-clause audit yet/)).toBeInTheDocument())
  })

  it('expanding a location row mounts the checklist for that pair', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    const user = userEvent.setup()
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText('Fresno')).toBeInTheDocument())
    expect(complianceApi.fetchRequirementComponents).not.toHaveBeenCalled()

    await user.click(screen.getByText('Fresno'))

    await waitFor(() => expect(complianceApi.fetchRequirementComponents).toHaveBeenCalledWith('loc-fresno', 'cat-1', undefined))
  })

  it('collapsing unmounts the checklist and re-expanding refetches', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    const user = userEvent.setup()
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText('Fresno')).toBeInTheDocument())
    await user.click(screen.getByText('Fresno'))
    await waitFor(() => expect(complianceApi.fetchRequirementComponents).toHaveBeenCalledTimes(1))

    await user.click(screen.getByText('Fresno'))  // collapse
    await user.click(screen.getByText('Fresno'))  // re-expand

    await waitFor(() => expect(complianceApi.fetchRequirementComponents).toHaveBeenCalledTimes(2))
  })

  it('targetCatalogId highlights the matching card and consumes the target', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    const onTargetConsumed = vi.fn()
    render(<ComplianceAuditTab targetCatalogId="cat-1" onTargetConsumed={onTargetConsumed} />)

    await waitFor(() => {
      const card = document.querySelector('[data-statute-id="cat-1"]')
      expect(card).toHaveClass('border-emerald-500/40')
    })
    expect(onTargetConsumed).toHaveBeenCalledTimes(1)
  })

  it('statute header reads as a conditional ceiling when nothing is non_compliant', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText(/If unproven, up to \$25,000 · Cal\/OSHA/)).toBeInTheDocument())
  })

  it('statute header reads as confirmed exposure once a location has a gap', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute({
      summary: {
        total: 10, known: 10, coverage_pct: 100, derived: 9, attested: 1,
        count_compliant: 9, count_non_compliant: 1, count_in_progress: 0, count_unknown: 0,
      },
    })]))
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText(/Exposure up to \$25,000 · Cal\/OSHA/)).toBeInTheDocument())
    expect(screen.queryByText(/If unproven/)).not.toBeInTheDocument()
  })

  it('readOnly hides every attest control in an expanded checklist', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    const user = userEvent.setup()
    render(<ComplianceAuditTab readOnly />)

    await waitFor(() => expect(screen.getByText('Fresno')).toBeInTheDocument())
    await user.click(screen.getByText('Fresno'))

    await waitFor(() => expect(screen.getAllByText('No evidence on file').length).toBe(2))
    expect(screen.queryByText('We have this')).not.toBeInTheDocument()
  })

  it('threads companyId through the overview fetch and down into an expanded checklist', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit).mockResolvedValue(overview([statute()]))
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    const user = userEvent.setup()
    render(<ComplianceAuditTab companyId="co-9" />)

    await waitFor(() => expect(complianceApi.fetchComplianceAudit).toHaveBeenCalledWith('co-9'))

    await waitFor(() => expect(screen.getByText('Fresno')).toBeInTheDocument())
    await user.click(screen.getByText('Fresno'))

    await waitFor(() => expect(complianceApi.fetchRequirementComponents).toHaveBeenCalledWith('loc-fresno', 'cat-1', 'co-9'))
  })

  it('a failed background refresh after attestation banners inline instead of clobbering the tab', async () => {
    vi.mocked(complianceApi.fetchComplianceAudit)
      .mockResolvedValueOnce(overview([statute()]))
      .mockRejectedValueOnce(new Error('boom'))
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    vi.mocked(complianceApi.attestRequirementComponent).mockResolvedValue({
      ...checklist().components[1], status: 'compliant', basis: 'attested',
    })
    const user = userEvent.setup()
    render(<ComplianceAuditTab />)

    await waitFor(() => expect(screen.getByText('Fresno')).toBeInTheDocument())
    await user.click(screen.getByText('Fresno'))
    await waitFor(() => expect(screen.getByText('We have this')).toBeInTheDocument())
    await user.click(screen.getByText('We have this'))

    await waitFor(() => expect(complianceApi.fetchComplianceAudit).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(
      screen.getByText('Could not refresh — showing the last loaded data.'),
    ).toBeInTheDocument())
    expect(screen.getByText('Workplace Violence Prevention Plan')).toBeInTheDocument()
    expect(screen.queryByText('Could not load the audit overview.')).not.toBeInTheDocument()
  })
})
