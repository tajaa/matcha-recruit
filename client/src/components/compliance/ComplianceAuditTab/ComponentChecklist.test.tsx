import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ComponentChecklist } from './ComponentChecklist'
import * as complianceApi from '../../../api/compliance/compliance'
import type { RequirementComponentChecklist } from '../../../types/compliance'

vi.mock('../../../api/compliance/compliance', () => ({
  fetchRequirementComponents: vi.fn(),
  attestRequirementComponent: vi.fn(),
}))

function checklist(overrides: Partial<RequirementComponentChecklist> = {}): RequirementComponentChecklist {
  return {
    jurisdiction_requirement_id: 'cat-1',
    location_id: 'loc-1',
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
  vi.mocked(complianceApi.fetchRequirementComponents).mockReset()
  vi.mocked(complianceApi.attestRequirementComponent).mockReset()
  // These tests exercise the static list, not the audit-reveal animation
  // (covered separately in AuditRevealModal.test.tsx) — pre-seed the
  // "already seen" key so the modal doesn't auto-open and steal focus.
  localStorage.setItem('matcha_audit_reveal_seen:loc-1:cat-1', '1')
})

describe('ComponentChecklist', () => {
  it('renders unknown status as "No evidence on file", never "GAP"', async () => {
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" />)

    await waitFor(() => expect(screen.getAllByText('No evidence on file').length).toBe(2))
    expect(screen.queryByText(/^GAP$/)).not.toBeInTheDocument()
  })

  it('hides the attest control when readOnly', async () => {
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" readOnly />)

    await waitFor(() => expect(screen.getAllByText('No evidence on file').length).toBe(2))
    expect(screen.queryByText('We have this')).not.toBeInTheDocument()
  })

  it('does not render an attest control for a derivable component', async () => {
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" />)

    await waitFor(() => expect(screen.getAllByText('No evidence on file').length).toBe(2))
    // Only the non-derivable component (hazard_assessment) gets an attest button.
    expect(screen.getAllByText('We have this')).toHaveLength(1)
  })

  it('renders a dash for null coverage, never "0%"', async () => {
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" />)

    await waitFor(() => expect(screen.getByText('—')).toBeInTheDocument())
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
  })

  it('attesting a non-derivable component calls the API and updates the row', async () => {
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    vi.mocked(complianceApi.attestRequirementComponent).mockResolvedValue({
      component_key: 'hazard_assessment',
      label: 'Hazard Assessment',
      question: 'Per-site assessment with workplace-specific hazards?',
      statute_citation: 'Cal. Lab. Code § 6401.9(b) (hazard identification)',
      suggested_fix: 'Schedule per-site hazard assessments.',
      severity: 'important',
      sort_order: 4,
      derivable: false,
      derivation_source: null,
      status: 'compliant',
      basis: 'attested',
      evidence: {},
      attested_note: null,
      attested_at: '2026-07-24T00:00:00Z',
      derived_at: null,
    })
    const user = userEvent.setup()
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" />)

    await waitFor(() => expect(screen.getByText('We have this')).toBeInTheDocument())
    await user.click(screen.getByText('We have this'))

    await waitFor(() => expect(complianceApi.attestRequirementComponent).toHaveBeenCalledWith(
      'loc-1', 'cat-1', 'hazard_assessment', { status: 'compliant' }, undefined,
    ))
    await waitFor(() => expect(screen.getAllByText('Compliant').length).toBe(1))
  })

  it('a failed attestation shows an inline error without erasing the checklist', async () => {
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist())
    vi.mocked(complianceApi.attestRequirementComponent).mockRejectedValue(new Error('409'))
    const user = userEvent.setup()
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" />)

    await waitFor(() => expect(screen.getByText('We have this')).toBeInTheDocument())
    await user.click(screen.getByText('We have this'))

    await waitFor(() => expect(screen.getByText('Could not save that attestation.')).toBeInTheDocument())
    // The clauses, rollup, and Replay control must all still be on screen —
    // an attest failure must not fall through to the load-error render path.
    expect(screen.getAllByText('No evidence on file').length).toBe(2)
    expect(screen.getByText('↻ Replay audit')).toBeInTheDocument()

    await user.click(screen.getByText('Dismiss'))
    expect(screen.queryByText('Could not save that attestation.')).not.toBeInTheDocument()
  })

  it('renders an attest control for the attest-only violent_incident_log clause', async () => {
    // Regression for dropping the wvp_incident_log derivation: this clause
    // used to be `derivable: true` with no escape hatch when its ILIKE match
    // false-positived. It is attest-only now, like hazard_assessment.
    vi.mocked(complianceApi.fetchRequirementComponents).mockResolvedValue(checklist({
      components: [{
        component_key: 'violent_incident_log',
        label: 'Violent Incident Log',
        question: 'Are incidents logged and retained for 5 years?',
        statute_citation: 'Cal. Lab. Code § 6401.9(c) (violent incident log)',
        suggested_fix: 'Deploy a violent-incident log with 5-year retention.',
        severity: 'critical',
        sort_order: 3,
        derivable: false,
        derivation_source: null,
        status: 'unknown',
        basis: null,
        evidence: {},
        attested_note: null,
        attested_at: null,
        derived_at: null,
      }],
    }))
    render(<ComponentChecklist locationId="loc-1" catalogId="cat-1" />)

    await waitFor(() => expect(screen.getByText('We have this')).toBeInTheDocument())
  })
})
