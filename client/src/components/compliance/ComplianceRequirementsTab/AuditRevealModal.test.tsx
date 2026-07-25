import { act, render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { AuditRevealModal, exposureLabel } from './AuditRevealModal'
import { weighingSteps } from './useAuditReveal'
import type { RequirementComponent, RequirementComponentChecklist, RequirementComponentSummary, RiskPenalty } from '../../../types/compliance'

function component(overrides: Partial<RequirementComponent> = {}): RequirementComponent {
  return {
    component_key: 'written_plan',
    label: 'Written WVP Plan',
    question: 'Is there a written plan?',
    statute_citation: 'Cal. Lab. Code § 6401.9(b)',
    suggested_fix: 'Draft a written plan.',
    severity: 'critical',
    sort_order: 1,
    derivable: false,
    derivation_source: null,
    status: 'unknown',
    basis: null,
    evidence: {},
    attested_note: null,
    attested_at: null,
    derived_at: null,
    ...overrides,
  }
}

function summaryFor(components: RequirementComponent[]): RequirementComponentSummary {
  const known = components.filter((c) => c.status !== 'unknown').length
  return {
    total: components.length, known,
    coverage_pct: components.length ? Math.round((known / components.length) * 100) : null,
    derived: 0, attested: known,
    count_compliant: components.filter((c) => c.status === 'compliant').length,
    count_non_compliant: components.filter((c) => c.status === 'non_compliant').length,
    count_in_progress: components.filter((c) => c.status === 'in_progress').length,
    count_unknown: components.filter((c) => c.status === 'unknown').length,
  }
}

function checklist(
  components: RequirementComponent[],
  overrides: Partial<Pick<RequirementComponentChecklist, 'exposure'>> = {},
): RequirementComponentChecklist {
  return {
    jurisdiction_requirement_id: 'cat-1',
    location_id: 'loc-1',
    title: 'Workplace Violence Prevention Plan',
    statute_citation: 'Cal. Lab. Code § 6401.9',
    components,
    summary: summaryFor(components),
    exposure: null,
    ...overrides,
  }
}

function penalty(overrides: Partial<RiskPenalty> = {}): RiskPenalty {
  return { civil_max: 25000, enforcing_agency: 'Cal/OSHA', grounded: true, ...overrides }
}

// Real timers, but every clause's per-step delay is bounded (min 420ms/n
// steps) — running the fake-timer clock forward past a generous ceiling
// deterministically reaches the 'done' phase without waiting wall-clock time.
async function runToCompletion() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(20_000)
  })
}

describe('AuditRevealModal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('resolves unknown to "No evidence on file" and never renders the string GAP', async () => {
    const c = checklist([component({ status: 'unknown' }), component({ component_key: 'hazard_assessment', status: 'unknown' })])
    render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)

    await runToCompletion()

    expect(screen.getAllByText('No evidence on file').length).toBeGreaterThan(0)
    expect(screen.queryByText('Gap')).not.toBeInTheDocument()
  })

  it('renders "Gap" for a real non_compliant verdict', async () => {
    const c = checklist([component({ status: 'non_compliant' })])
    render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)

    await runToCompletion()

    expect(screen.getByText('Gap')).toBeInTheDocument()
  })

  it('lays out any number of components, not just 5', async () => {
    const c = checklist([
      component({ component_key: 'a', label: 'A' }),
      component({ component_key: 'b', label: 'B' }),
    ])
    render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })

  it('skip jumps straight to the resolved state', async () => {
    const c = checklist([component({ status: 'compliant' })])
    render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)

    await act(async () => {
      screen.getByText('Skip').click()
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(screen.getByText('Compliant')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    const c = checklist([component()])
    render(<AuditRevealModal open={false} onClose={() => {}} checklist={c} runId={0} />)
    expect(screen.queryByText('Written WVP Plan')).not.toBeInTheDocument()
  })

  // ── Replay / re-run race (useAuditReveal's per-run cancellation token) ────
  // Before the fix, a shared cancelledRef reset to `false` at the top of the
  // new effect un-cancelled the STALE run the instant its suspended `sleep()`
  // woke up, and that stale run's own `finish()` then slammed every clause
  // to 'remediated' — clobbering whatever the new run had drawn so far.

  it('a stale run cannot finish() after Replay starts a new one', async () => {
    const c = checklist([component({ status: 'unknown' }), component({ component_key: 'hazard_assessment', status: 'unknown' })])
    const { rerender } = render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)

    // Let run 0 get partway into fanning, then Replay (new runId) before it
    // would naturally finish.
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    rerender(<AuditRevealModal open onClose={() => {}} checklist={c} runId={1} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(300) })

    // If the stale run's finish() fired, the HUD would already read "Analysis
    // complete" and every clause would already be committed — neither should
    // be true this early into the fresh run.
    expect(screen.queryByText(/Analysis complete/)).not.toBeInTheDocument()
    expect(screen.queryAllByText('No evidence on file').length).toBe(0)
  })

  it('close then reopen with a new runId does not let the closed run finish() later', async () => {
    const c = checklist([component({ status: 'unknown' })])
    const { rerender } = render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)

    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    rerender(<AuditRevealModal open={false} onClose={() => {}} checklist={c} runId={0} />)
    rerender(<AuditRevealModal open onClose={() => {}} checklist={c} runId={1} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(300) })

    expect(screen.queryByText(/Analysis complete/)).not.toBeInTheDocument()
  })

  it('unmounting mid-run does not warn about updating state after unmount', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const c = checklist([component({ status: 'unknown' }), component({ component_key: 'hazard_assessment', status: 'unknown' })])
    const { unmount } = render(<AuditRevealModal open onClose={() => {}} checklist={c} runId={0} />)

    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000) })

    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  // ── header: no hardcoded location count, no doubled separator ────────────

  it('does not print "1 location" and does not double the separator when exposure is null', () => {
    const c = checklist([component()])
    render(<AuditRevealModal open onClose={() => {}} checklist={c} employeeCount={12} runId={0} />)

    expect(screen.queryByText(/1 location/)).not.toBeInTheDocument()
    expect(screen.getByText(/Cal\. Lab\. Code § 6401\.9 · 12 employees · last activity: never/)).toBeInTheDocument()
  })
})

describe('exposureLabel', () => {
  it('reads as a conditional ceiling when nothing is proven non_compliant', () => {
    const summary = summaryFor([component({ status: 'unknown' })])
    expect(exposureLabel(summary, penalty())).toBe('If unproven, up to $25,000 · Cal/OSHA · directional')
  })

  it('reads as confirmed exposure once a clause is non_compliant', () => {
    const summary = summaryFor([component({ status: 'non_compliant' })])
    expect(exposureLabel(summary, penalty())).toBe('Exposure up to $25,000 · Cal/OSHA · directional')
  })

  it('is null with no penalty on file', () => {
    const summary = summaryFor([component({ status: 'unknown' })])
    expect(exposureLabel(summary, null)).toBeNull()
  })
})

describe('weighingSteps', () => {
  it('names the server-provided source for a derivable component', () => {
    const c = component({ derivable: true, derivation_source: 'training_records' })
    expect(weighingSteps(c)).toEqual(['Matching statute', 'Screening training_records', 'Scoring'])
  })

  it('falls back to "company records" when a derivable component has no source label', () => {
    const c = component({ derivable: true, derivation_source: null })
    expect(weighingSteps(c)).toEqual(['Matching statute', 'Screening company records', 'Scoring'])
  })

  it('reads as attest-only for a non-derivable component', () => {
    const c = component({ derivable: false })
    expect(weighingSteps(c)).toEqual(['Matching statute', 'No system record', 'Awaiting attestation'])
  })
})
