import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import LeadPane from './LeadPane'
import type { JobLeadDetail } from '../../api/matchaWork/jobSearch'

const job = (over: Partial<JobLeadDetail> = {}): JobLeadDetail => ({
  id: 'l1', title: 'COO', company: 'Acme', location: 'Austin, TX', remote: null, source_url: null, apply_url: null,
  posted_text: null, comp_line: '$250K', comp_status: 'posted', fit_score: 4, screen_status: 'relevant', rank: 1,
  rank_band: 0, flags: [], user_state: 'new', approach_status: 'done', email_draft_id: null, email_drafted_at: null,
  email_sent_at: null, description: '', comp: null, pay_law_hint: null, screen_reason: null, fit_reasons: [],
  approach: { summary: 'Go through the CEO.', outreach: { subject: 'The COO role', body: 'Hi Jane' } }, notes: '', ...over,
})

function pane(props: Partial<Parameters<typeof LeadPane>[0]> = {}) {
  const handlers = { onRetry: vi.fn(), onDismissError: vi.fn(), onClose: vi.fn(), onDraftEmail: vi.fn(), onEditDraft: vi.fn() }
  render(
    <MemoryRouter>
      <LeadPane
        lead={null}
        loadError={null}
        error={null}
        canDraft
        busy={false}
        emailNotConnected={false}
        emailDrafted={false}
        emailDraftGone={false}
        emailPath="/espresso/email"
        onSetState={vi.fn()}
        onSaveNotes={vi.fn()}
        onRedraft={vi.fn()}
        onAskEspresso={vi.fn()}
        {...handlers}
        {...props}
      />
    </MemoryRouter>,
  )
  return handlers
}

describe('LeadPane', () => {
  it('spins while the job loads', () => {
    pane()
    expect(screen.getByLabelText('Loading')).toBeTruthy()
  })

  it("says the job couldn't load and tries again", () => {
    const { onRetry } = pane({ loadError: "Couldn't load this job." })
    expect(screen.queryByLabelText('Loading')).toBeNull()
    expect(screen.getByText("Couldn't load this job.")).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it("shows a change that didn't go through over the job, and dismisses it", () => {
    const { onDismissError } = pane({ lead: job(), error: "Couldn't save that." })
    expect(screen.getByRole('alert').textContent).toContain("Couldn't save that.")
    expect(screen.getByText('COO')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss the message' }))
    expect(onDismissError).toHaveBeenCalledOnce()
  })

  it('opens a draft in Gmail without asking for a new one', () => {
    const { onEditDraft, onDraftEmail } = pane({ lead: job({ email_draft_id: 'r-1' }) })
    fireEvent.click(screen.getByRole('button', { name: /Edit draft in Gmail/ }))
    expect(onEditDraft).toHaveBeenCalledWith('l1')
    expect(onDraftEmail).not.toHaveBeenCalled()
  })

  it('says a draft left Gmail, and Draft email makes a new one', () => {
    const { onEditDraft, onDraftEmail } = pane({ lead: job(), emailDraftGone: true })
    expect(screen.getByText(/isn't in your Gmail drafts any more/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Draft email/ }))
    expect(onDraftEmail).toHaveBeenCalledWith('l1')
    expect(onEditDraft).not.toHaveBeenCalled()
  })
})

describe('LeadPane drafting controls', () => {
  it('offers no Redraft on a search that cannot draft', () => {
    pane({ lead: job(), canDraft: false })
    expect(screen.queryByRole('button', { name: 'Redraft' })).toBeNull()
  })

  it('lists the questions left for the person, with why', () => {
    pane({ lead: job({ approach: { summary: 'x', unanswered: [
      { question_key: 'resume', question: 'Resume/CV', kind: 'file' },
      { question_key: 'auth', question: 'Are you authorized to work in the US?', kind: 'authorization' },
    ] } }) })
    expect(screen.getByText(/Resume\/CV/).textContent).toContain('(a file to upload)')
    expect(screen.getByText(/authorized to work/).textContent).toContain('(work authorization)')
  })
})
