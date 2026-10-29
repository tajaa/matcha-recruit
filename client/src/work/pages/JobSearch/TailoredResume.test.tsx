import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import TailoredResumeSection from './TailoredResume'
import { resumeFileName } from './jobSearchLogic'
import type { JobLeadDetail, TailoredResume } from '../../api/matchaWork/jobSearch'

const tailored = (over: Partial<TailoredResume> = {}): TailoredResume => ({
  summary: { text: 'Operations leader who has run multi-site teams.', sources: ['Ran a 40-person team.'] },
  experience: [{
    role: 'Operations Director', organization: 'Acme Logistics', dates: '2019 - 2024',
    bullets: [{ text: 'Cut carrier costs 18%.', sources: ['Cut shipping costs by 18% by renegotiating carrier contracts.'] }],
  }],
  skills: ['SAP', 'vendor negotiation'],
  sections: [{ heading: 'Education', lines: [{ text: 'MBA, State University', sources: ['MBA, State University, 2014'] }] }],
  changes: ['Put the carrier work first.'],
  gaps: ['The posting asks for SQL; your résumé doesn’t mention it.'],
  dropped: 2,
  resume_saved_at: '2026-10-01T00:00:00+00:00',
  made_at: '2026-10-29T00:00:00+00:00',
  text: 'SUMMARY\nOperations leader who has run multi-site teams.',
  ...over,
})

const job = (over: Partial<JobLeadDetail> = {}): JobLeadDetail => ({
  id: 'l1', title: 'COO', company: 'Acme', location: 'Austin, TX', remote: null, source_url: null, apply_url: null,
  posted_text: null, comp_line: '$250K', comp_status: 'posted', fit_score: 4, screen_status: 'relevant', rank: 1,
  rank_band: 0, flags: [], user_state: 'new', approach_status: 'done', email_draft_id: null, email_drafted_at: null,
  email_sent_at: null, description: '', comp: null, pay_law_hint: null, screen_reason: null, fit_reasons: [],
  approach: null, notes: '', resume_status: 'none', tailored_resume: null, ...over,
})

function section(lead: JobLeadDetail, busy = false) {
  const onTailor = vi.fn()
  render(
    <MemoryRouter>
      <TailoredResumeSection lead={lead} busy={busy} resumePath="/espresso/tasks?view=resume" onTailor={onTailor} />
    </MemoryRouter>,
  )
  return onTailor
}

describe('TailoredResumeSection', () => {
  it('offers to tailor, and links to the saved résumé', () => {
    const onTailor = section(job())
    expect(screen.getByRole('link', { name: 'Your résumé' }).getAttribute('href')).toBe('/espresso/tasks?view=resume')
    fireEvent.click(screen.getByRole('button', { name: 'Tailor my résumé' }))
    expect(onTailor).toHaveBeenCalledWith('l1')
  })

  it('spins while it is tailored, with nothing to click', () => {
    section(job({ resume_status: 'drafting' }))
    expect(screen.getByText('Rewriting your résumé for this posting…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Tailor/ })).toBeNull()
  })

  it("says a run that didn't finish can be tried again", () => {
    section(job({ resume_status: 'failed' }))
    expect(screen.getByText(/Tailoring didn't finish for this job/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Tailor my résumé' })).toBeTruthy()
  })

  it('shows the résumé, where each line came from, what changed and what is missing', () => {
    section(job({ resume_status: 'done', tailored_resume: tailored() }))
    expect(screen.getByText('Operations leader who has run multi-site teams.')).toBeTruthy()
    expect(screen.getByText('Operations Director — Acme Logistics')).toBeTruthy()
    expect(screen.getByText('Cut carrier costs 18%.')).toBeTruthy()
    expect(screen.getByText('From your résumé: “Cut shipping costs by 18% by renegotiating carrier contracts.”')).toBeTruthy()
    expect(screen.getByText('Put the carrier work first.', { exact: false })).toBeTruthy()
    expect(screen.getByText(/The posting asks for SQL/)).toBeTruthy()
    expect(screen.getByText(/2 lines were left out because they didn't match your résumé/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Tailor again' })).toBeTruthy()
  })

  it('edits on the page, and Copy takes the edits', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    section(job({ resume_status: 'done', tailored_resume: tailored() }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    const box = screen.getByRole('textbox', { name: 'Your tailored résumé' })
    fireEvent.change(box, { target: { value: 'My own words' } })
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith('My own words')
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeTruthy()
    expect(screen.getByText(/Your edits aren't saved/)).toBeTruthy()
  })

  it('downloads the text as a file named for the job', () => {
    const create = vi.fn(() => 'blob:x')
    const revoke = vi.fn()
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    section(job({ resume_status: 'done', tailored_resume: tailored() }))
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))
    expect(create).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(revoke).toHaveBeenCalledWith('blob:x')
    click.mockRestore()
  })
})

describe('resumeFileName', () => {
  it('names the file for the job, safely', () => {
    expect(resumeFileName({ company: 'Acme, Inc.', title: 'COO / President' })).toBe('Resume - Acme, Inc. - COO President.txt')
    expect(resumeFileName({ company: '', title: 'Café Manager' })).toBe('Resume - Café Manager.txt')
  })
})
