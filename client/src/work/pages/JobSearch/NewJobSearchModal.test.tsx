import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NewJobSearchModal from './NewJobSearchModal'
import type { ProfileResume } from '../../../api/profileResume'
import type { JobSearchList } from '../../api/matchaWork/jobSearch'

const mock = vi.hoisted(() => ({ get: vi.fn(), upload: vi.fn() }))
vi.mock('../../../api/profileResume', () => ({ getMyResume: mock.get, uploadMyResume: mock.upload }))

const list: JobSearchList = { searches: [], usage: null, consent: { granted: true, disclosure: null }, available: true }
const uploaded = { filename: 'jane-doe.pdf', parsed_data: null } as unknown as ProfileResume

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

describe('NewJobSearchModal résumé', () => {
  it("keeps a résumé uploaded while the saved one's read was still out", async () => {
    const saved = deferred<ProfileResume | null>()
    mock.get.mockReturnValue(saved.promise)
    mock.upload.mockResolvedValue(uploaded)
    const onCreate = vi.fn().mockResolvedValue({ id: 's1' })
    const { container } = render(<NewJobSearchModal list={list} onCreate={onCreate} onCreated={vi.fn()} onClose={vi.fn()} />)

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['resume'], 'jane-doe.pdf', { type: 'application/pdf' })
    await act(async () => { fireEvent.change(input, { target: { files: [file] } }) })
    expect(screen.getByText('jane-doe.pdf')).toBeTruthy()

    // The first read answers late, from before the upload: no résumé saved.
    await act(async () => { saved.resolve(null) })
    expect(screen.getByText('jane-doe.pdf')).toBeTruthy()
    const use = screen.getByRole('checkbox', { name: /Use my résumé/ }) as HTMLInputElement
    expect(use.checked).toBe(true)

    fireEvent.change(screen.getByLabelText('What are you looking for?'), { target: { value: 'COO roles in Austin' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Start search' })) })
    expect(onCreate).toHaveBeenCalledOnce()
    expect(onCreate.mock.calls[0][0].use_resume).toBe(true)
  })

  it('still shows the saved résumé when an upload fails', async () => {
    const saved = deferred<ProfileResume | null>()
    mock.get.mockReturnValue(saved.promise)
    mock.upload.mockRejectedValue(new Error('too big'))
    const { container } = render(<NewJobSearchModal list={list} onCreate={vi.fn()} onCreated={vi.fn()} onClose={vi.fn()} />)

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    await act(async () => { fireEvent.change(input, { target: { files: [new File(['x'], 'big.pdf')] } }) })
    await act(async () => { saved.resolve({ ...uploaded, filename: 'saved.pdf' }) })
    expect(screen.getByText('saved.pdf')).toBeTruthy()
    expect((screen.getByRole('checkbox', { name: /Use my résumé/ }) as HTMLInputElement).checked).toBe(true)
  })
})

describe('NewJobSearchModal title', () => {
  it("cuts the search's title to what the server takes", async () => {
    mock.get.mockResolvedValue(null)
    const onCreate = vi.fn().mockResolvedValue({ id: 's1' })
    render(<NewJobSearchModal list={list} onCreate={onCreate} onCreated={vi.fn()} onClose={vi.fn()} />)
    await act(async () => {})
    fireEvent.change(screen.getByLabelText('What are you looking for?'), { target: { value: 'COO roles' } })
    const titles = screen.getByLabelText(/Titles/i)
    fireEvent.change(titles, { target: { value: 'x'.repeat(78) + ' ' + 'y'.repeat(60) } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Start search' })) })
    expect(onCreate).toHaveBeenCalledOnce()
    expect(onCreate.mock.calls[0][0].title.length).toBeLessThanOrEqual(120)
  })
})
