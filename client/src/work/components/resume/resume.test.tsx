import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { resetAuthCaches } from '../../../api/authReset'
import { ApiError } from '../../../api/client'
import type { MyResume } from '../../../api/profileResume'
import { WorkSurfaceProvider } from '../../routes/WorkSurfaceContext'
import type { IntakeForm } from '../../types'
import { IntakeFormCard } from '../tasks/TaskChatCards'
import ResumePane from './ResumePane'

const api = vi.hoisted(() => ({ get: vi.fn(), upload: vi.fn(), save: vi.fn(), remove: vi.fn() }))
vi.mock('../../../api/profileResume', () => ({
  getMyResume: api.get, uploadMyResume: api.upload, updateMyResumeText: api.save, deleteMyResume: api.remove,
}))
vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ me: { user: { id: 'u1' } }, isPersonal: true }) }))
const answer = vi.hoisted(() => vi.fn())
vi.mock('../../api/matchaWork/agentTasks', () => ({ answerAgentTaskForm: answer }))

const TEXT = 'Haley Rivera. Senior Software Engineer, Platform & AI at Northwind Labs. Seven years at startups.'
const saved = (over: Partial<MyResume> = {}): MyResume => ({
  filename: 'Haley-Rivera-Resume.pdf', resume_url: 'https://signed.test/cv.pdf?ttl=900', updated_at: '2026-10-18T22:00:00Z',
  parsed_data: { current_title: 'Senior Software Engineer', experience_years: 7, location: 'San Francisco, CA',
    skills: ['TypeScript', 'Kubernetes'], summary: 'Builds platforms and LLM products.' },
  text: TEXT, ...over,
})
const pdf = (name = 'cv.pdf', type = 'application/pdf') => new File(['%PDF-1.7 résumé'], name, { type })

function wrap(node: React.ReactNode) {
  return render(<MemoryRouter><WorkSurfaceProvider value="espresso">{node}</WorkSurfaceProvider></MemoryRouter>)
}

beforeEach(() => { resetAuthCaches() })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('ResumePane', () => {
  it('takes a dropped-in résumé and shows the text Espresso will read', async () => {
    api.get.mockResolvedValue(null)
    api.upload.mockResolvedValue(saved())
    wrap(<ResumePane />)
    expect(await screen.findByText('Drop your résumé here, or choose a file')).toBeTruthy()
    expect(screen.getByText(/Private to you\. The file is stored encrypted/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Choose a résumé file'), { target: { files: [pdf('photo.png', 'image/png')] } })
    expect((await screen.findByRole('alert')).textContent).toContain('PDF, Word or text')
    expect(api.upload).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Choose a résumé file'), { target: { files: [pdf()] } })
    expect(await screen.findByText('Haley-Rivera-Resume.pdf')).toBeTruthy()
    expect((screen.getByLabelText('The text Espresso uses') as HTMLTextAreaElement).value).toBe(TEXT)
    expect(screen.getByText('Saved. Espresso read it again.')).toBeTruthy()
    expect(screen.getByText('Kubernetes')).toBeTruthy()
  })

  it('edits the text in place, and can discard an edit', async () => {
    api.get.mockResolvedValue(saved())
    api.save.mockImplementation((text: string) => Promise.resolve(saved({ text })))
    wrap(<ResumePane />)
    const box = await screen.findByLabelText('The text Espresso uses') as HTMLTextAreaElement
    const save = screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.change(box, { target: { value: `${TEXT} Also led customer integrations.  ` } })
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(box.value).toBe(TEXT)
    fireEvent.change(box, { target: { value: 'Too short' } })
    fireEvent.click(save)
    expect((await screen.findByRole('alert')).textContent).toContain('at least a few lines')
    expect(api.save).not.toHaveBeenCalled()
    fireEvent.change(box, { target: { value: `${TEXT} Also led customer integrations.  ` } })
    fireEvent.click(save)
    await screen.findByText('Saved. New job searches read this text.')
    expect(api.save).toHaveBeenCalledWith(`${TEXT} Also led customer integrations.`)
    expect(box.value).toBe(`${TEXT} Also led customer integrations.`)
  })

  it('opens the original through a fresh link, and deletes only once confirmed', async () => {
    api.get.mockResolvedValue(saved())
    const tab = { opener: {} as unknown, location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    wrap(<ResumePane />)
    fireEvent.click(await screen.findByRole('button', { name: /Open original/ }))
    await waitFor(() => expect(tab.location.href).toBe('https://signed.test/cv.pdf?ttl=900'))
    expect(tab.opener).toBeNull()
    expect(api.get).toHaveBeenCalledTimes(2) // a fresh fifteen-minute link

    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(screen.getByRole('button', { name: /Delete/ }))
    expect(api.remove).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    api.remove.mockResolvedValue(undefined)
    fireEvent.click(screen.getByRole('button', { name: /Delete/ }))
    expect(await screen.findByText('Drop your résumé here, or choose a file')).toBeTruthy()
  })

  it('says why a file was refused', async () => {
    api.get.mockResolvedValue(null)
    api.upload.mockRejectedValue(new ApiError('bad', 422, { detail: 'Could not parse resume. Please try a different file or format.' }))
    wrap(<ResumePane />)
    fireEvent.change(await screen.findByLabelText('Choose a résumé file'), { target: { files: [pdf()] } })
    expect((await screen.findByRole('alert')).textContent).toBe('Could not parse resume. Please try a different file or format.')
  })
})

const jobForm = (value: unknown): IntakeForm => ({
  playbook: 'job_search', label: 'Job search', units: 5, submit_label: 'Start',
  fields: [{ key: 'use_resume', label: 'Use my résumé', type: 'boolean', widget: 'resume', value }],
  known: [{ key: 'titles', label: 'Job titles', shown: 'Full stack engineer' }],
})

function openForm(value: unknown = 'yes') {
  return wrap(<IntakeFormCard question="A few details" form={jobForm(value)} promptId="p1" status="open"
    closedText="Answered" mine channelId="c1" />)
}

describe('the résumé in a job search form', () => {
  it('asks for one to be dropped in, and starts only once it is saved', async () => {
    api.get.mockResolvedValue(null)
    api.upload.mockResolvedValue(saved())
    answer.mockResolvedValue({ id: 't1', status: 'queued' })
    openForm()
    expect(await screen.findByText('Drop your résumé here to use it')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Drop in your résumé')
    expect(answer).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Choose a résumé file'), { target: { files: [pdf()] } })
    expect(await screen.findByText('Haley-Rivera-Resume.pdf')).toBeTruthy()
    expect(screen.getByText('saved')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'View or edit' }).getAttribute('href')).toBe('/espresso/tasks?view=resume')
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    await waitFor(() => expect(answer).toHaveBeenCalled())
    expect(answer.mock.calls[0][1].values).toEqual({ use_resume: true })
  })

  it('shows the saved one, and a general search needs none', async () => {
    api.get.mockResolvedValue(saved())
    openForm()
    expect(await screen.findByText('will be used')).toBeTruthy()
    fireEvent.click(screen.getByRole('switch'))
    expect(screen.getByText('not used')).toBeTruthy()
    cleanup(); resetAuthCaches()
    api.get.mockResolvedValue(null)
    answer.mockResolvedValue({ id: 't2', status: 'queued' })
    openForm('')
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(screen.queryByText('Drop your résumé here to use it')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    await waitFor(() => expect(answer).toHaveBeenCalled())
  })
})
