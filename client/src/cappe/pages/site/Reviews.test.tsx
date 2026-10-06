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

function load(reviews: CappeReview[] | Error, who: string | Error = 'anyone') {
  api.get.mockImplementation((path: string) => {
    const value = path.endsWith('/review-settings') ? (who instanceof Error ? who : { submissions: who }) : reviews
    return value instanceof Error ? Promise.reject(value) : Promise.resolve(value)
  })
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
    api.put.mockRejectedValueOnce(new Error('Server error'))
    fireEvent.change(select, { target: { value: 'off' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
    expect(select).toHaveValue('buyers')
  })

  it('shows a load error with a retry instead of spinning forever', async () => {
    load(new Error('Server error'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load your reviews')
    expect(screen.queryByText(/No pending reviews/)).not.toBeInTheDocument()
    api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/review-settings') ? { submissions: 'anyone' } : [REVIEW]))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Lovely mug')).toBeInTheDocument()
  })
})
