import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Reviews from './Reviews'
import type { CappeReview } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api }))

const REVIEW: CappeReview = {
  id: 'r-1', site_id: 's-1', author_name: 'Ana', rating: 5, body: 'Lovely mug', status: 'pending',
  created_at: '2026-10-01T00:00:00Z', product_id: 'p-1', product_name: 'Mug', verified: true,
  owner_reply: null, owner_replied_at: null,
}

// The page asks for one tab at a time (`?status=`) and for the tab counts.
function answer(reviews: CappeReview[] | Error, who: string | Error = 'anyone', counts?: Record<string, number>) {
  return (path: string) => {
    let value: unknown
    if (path.endsWith('/review-settings')) value = who instanceof Error ? who : { submissions: who }
    else if (path.endsWith('/reviews/counts')) {
      value = counts ?? (reviews instanceof Error ? reviews : {
        pending: reviews.filter((r) => r.status === 'pending').length,
        approved: reviews.filter((r) => r.status === 'approved').length,
        hidden: reviews.filter((r) => r.status === 'hidden').length,
      })
    } else {
      const status = new URLSearchParams(path.split('?')[1]).get('status')
      value = reviews instanceof Error ? reviews : reviews.filter((r) => r.status === status)
    }
    return value instanceof Error ? Promise.reject(value) : Promise.resolve(value)
  }
}

function load(reviews: CappeReview[] | Error, who: string | Error = 'anyone', counts?: Record<string, number>) {
  api.get.mockImplementation(answer(reviews, who, counts))
  render(
    <MemoryRouter initialEntries={['/sites/s-1/reviews']}>
      <Routes><Route path="/sites/:siteId/reviews" element={<Reviews />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.get.mockReset(); api.patch.mockReset(); api.put.mockReset(); api.delete.mockReset()
})

describe('Reviews', () => {
  it('shows what a review is about and that it came from a buyer', async () => {
    load([REVIEW])
    expect(await screen.findByText('Lovely mug')).toBeInTheDocument()
    expect(screen.getByText('About Mug')).toBeInTheDocument()
    expect(screen.getByText('Verified purchase')).toBeInTheDocument()
  })

  it('replies publicly', async () => {
    load([REVIEW])
    fireEvent.click(await screen.findByRole('button', { name: 'Reply publicly' }))
    fireEvent.change(screen.getByLabelText('Your reply'), { target: { value: 'Thank you!' } })
    api.put.mockResolvedValue({ ...REVIEW, owner_reply: 'Thank you!' })
    fireEvent.click(screen.getByRole('button', { name: 'Save reply' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/reviews/r-1/reply', { reply: 'Thank you!' }))
    expect(await screen.findByText(/Thank you!/)).toBeInTheDocument()
  })

  it('sets who can post, and puts it back if the save fails', async () => {
    load([REVIEW])
    const select = await screen.findByLabelText(/Who can post reviews/)
    api.put.mockResolvedValueOnce({ submissions: 'buyers' })
    fireEvent.change(select, { target: { value: 'buyers' } })
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/review-settings', { submissions: 'buyers' }))
    await waitFor(() => expect(select).not.toBeDisabled())
    api.put.mockRejectedValueOnce(new Error('Server error'))
    fireEvent.change(select, { target: { value: 'off' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
    expect(select).toHaveValue('buyers')
  })

  it('shows a load error with a retry instead of spinning forever', async () => {
    load(new Error('Server error'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load your reviews')
    expect(screen.queryByText(/No pending reviews/)).not.toBeInTheDocument()
    api.get.mockImplementation(answer([REVIEW]))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Lovely mug')).toBeInTheDocument()
  })

  it('saves who can post one change at a time', async () => {
    // Two saves in flight could land in either order: the store stayed open
    // to anyone while this said "Nobody".
    load([REVIEW], 'buyers')
    const select = await screen.findByLabelText(/Who can post reviews/)
    let finish: (v: unknown) => void = () => {}
    api.put.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    fireEvent.change(select, { target: { value: 'anyone' } })
    expect(select).toBeDisabled()
    fireEvent.change(select, { target: { value: 'off' } })
    expect(api.put).toHaveBeenCalledTimes(1)
    finish({ submissions: 'anyone' })
    await waitFor(() => expect(select).not.toBeDisabled())
    expect(select).toHaveValue('anyone')
  })

  it('loads each tab from the server and counts every review, not just a page', async () => {
    load([REVIEW], 'anyone', { pending: 1, approved: 1200, hidden: 0 })
    expect(await screen.findByText('Lovely mug')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/reviews?status=pending&limit=100&offset=0')
    const approved = screen.getByRole('button', { name: /Approved/ })
    expect(approved).toHaveTextContent('1200')
    fireEvent.click(approved)
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/sites/s-1/reviews?status=approved&limit=100&offset=0'))
    expect(await screen.findByText('No approved reviews.')).toBeInTheDocument()
  })

  it('pages back to the oldest reviews', async () => {
    const page = Array.from({ length: 100 }, (_, i) => ({ ...REVIEW, id: `r-${i}`, body: `Review ${i}` }))
    const older = { ...REVIEW, id: 'r-old', body: 'From years ago' }
    api.get.mockImplementation((path: string) => (path.includes('offset=100') ? Promise.resolve([page[99], older]) : answer(page)(path)))
    render(
      <MemoryRouter initialEntries={['/sites/s-1/reviews']}>
        <Routes><Route path="/sites/:siteId/reviews" element={<Reviews />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('From years ago')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/reviews?status=pending&limit=100&offset=100')
    expect(screen.getAllByText('Review 99')).toHaveLength(1)     // a review that shifted pages shows once
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('approving moves a review out of Pending and into the Approved count', async () => {
    load([REVIEW])
    await screen.findByText('Lovely mug')
    api.patch.mockResolvedValue({ ...REVIEW, status: 'approved' })
    fireEvent.click(screen.getByTitle('Approve'))
    expect(await screen.findByText('No pending reviews.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pending/ })).toHaveTextContent('0')
    expect(screen.getByRole('button', { name: /Approved/ })).toHaveTextContent('1')
  })
})
