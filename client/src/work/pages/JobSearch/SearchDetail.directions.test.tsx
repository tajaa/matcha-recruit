import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { WorkSurfaceProvider } from '../../routes/WorkSurfaceContext'
import type { JobLeadSummary, JobSearchDetail } from '../../api/matchaWork/jobSearch'
import SearchDetail from './SearchDetail'

vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: true, me: { user: { id: 'u1' } } }) }))
vi.mock('../../hooks/useRecapPreferences', () => ({ useRecapPreferences: () => null }))

const lead = (id: string, title: string, direction: string | null = null): JobLeadSummary => ({
  id, title, company: 'Acme', location: 'San Francisco, CA', remote: false, source_url: null, apply_url: null,
  posted_text: null, comp_line: '$180K–$220K', comp_status: 'posted', fit_score: 4, screen_status: 'relevant',
  rank: Number(id.slice(1)), rank_band: 0, flags: [], user_state: 'new', approach_status: 'none',
  email_draft_id: null, email_drafted_at: null, email_sent_at: null, direction,
})

const detail = (over: Partial<JobSearchDetail> = {}): JobSearchDetail => ({
  id: 's1', title: 'Full stack roles', ask: 'Full stack roles in CA', status: 'done', progress: null, error: null,
  lead_count: 3, posted_pay_count: 3, weights: null, use_resume: true, created_at: null, fit_floor: 4, fingerprint: 'f',
  leads: [lead('j1', 'Senior Full Stack Engineer'), lead('j2', 'Solutions Architect, AI', 'Solutions Architect'),
    lead('j3', 'Staff Engineer')],
  plan: { directions: [
    { title: 'Solutions Architect', why: "You've been the technical lead on 20+ enterprise calls.",
      evidence: 'Joined 20+ enterprise customer calls as the technical lead' },
    { title: 'Engineering Manager', why: 'You already lead a platform group.', evidence: 'Led a 4-engineer platform group' },
  ] },
  ...over,
})

function show(d: JobSearchDetail) {
  return render(
    <MemoryRouter><WorkSurfaceProvider value="espresso">
      <SearchDetail detail={d} busy={false} error={null} onDismissError={vi.fn()} selectedLeadId={null}
        onSelectLead={vi.fn()} onRerank={vi.fn()} onWiden={vi.fn()} onCancel={vi.fn()} onDelete={vi.fn()}
        onBack={vi.fn()} onHelp={vi.fn()} />
    </WorkSurfaceProvider></MemoryRouter>,
  )
}

afterEach(cleanup)

describe('roles beyond their title', () => {
  it('says what the résumé supports, in its own words, and shows the jobs for one', () => {
    show(detail())
    const card = screen.getByRole('region', { name: 'Beyond your title' })
    expect(within(card).getByText("You've been the technical lead on 20+ enterprise calls.")).toBeTruthy()
    expect(within(card).getByText('From your résumé: “Joined 20+ enterprise customer calls as the technical lead”')).toBeTruthy()
    expect(within(card).getByText('No jobs yet')).toBeTruthy() // Engineering Manager
    expect(screen.getAllByText('Beyond your title')).toHaveLength(2) // the card's heading and the one job's tag
    expect(screen.getByText('3 of 3')).toBeTruthy()
    fireEvent.click(within(card).getByRole('button', { name: '1 job' }))
    expect(screen.getByText('1 of 3')).toBeTruthy()
    expect(screen.queryByText('Senior Full Stack Engineer')).toBeNull()
    fireEvent.click(screen.getByLabelText('Show every job'))
    expect(screen.getByText('3 of 3')).toBeTruthy()
  })

  it('shows nothing extra for a search without them', () => {
    show(detail({ plan: {}, leads: [lead('j1', 'Senior Full Stack Engineer')] }))
    expect(screen.queryByRole('region', { name: 'Beyond your title' })).toBeNull()
    expect(screen.queryByText('Beyond your title')).toBeNull()
  })
})
