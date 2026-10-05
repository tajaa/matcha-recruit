import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EditorHeader } from '../pages/CappeSiteEditor/EditorHeader'
import type { CappeReadiness, CappeSite } from '../types'
import SetupGuide from './SetupGuide'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

const site = { id: 'site-1', name: 'Corner Bakery', slug: 'corner-bakery', subdomain: 'corner-bakery', custom_domain: null, status: 'draft' } as unknown as CappeSite

function readiness(contentDone: boolean): CappeReadiness {
  return {
    ready: contentDone,
    items: [
      { key: 'content', required: true, done: contentDone, action: 'pages', label: 'Add an intro / about section', hint: 'Tell visitors who you are.' },
      { key: 'offering', required: false, done: false, action: 'shop', label: 'Add something to book or buy', hint: 'What people pay you for.' },
    ],
  }
}

function renderGuide(onReadiness = vi.fn()) {
  render(
    <MemoryRouter>
      <SetupGuide site={site} pages={[]} publishing={false} onPublish={vi.fn()} onReadiness={onReadiness} />
    </MemoryRouter>,
  )
  return onReadiness
}

beforeEach(() => { api.get.mockReset() })

describe('SetupGuide', () => {
  it('lets a site with content publish with nothing to sell yet', async () => {
    api.get.mockResolvedValue(readiness(true))
    const onReadiness = renderGuide()

    expect(await screen.findByRole('button', { name: /Publish site/ })).toBeEnabled()
    expect(screen.getByText('Ready to publish')).toBeInTheDocument()
    // Still suggested, under Recommended.
    expect(screen.getByText('Add something to book or buy')).toBeInTheDocument()
    await waitFor(() => expect(onReadiness).toHaveBeenCalledWith(true))
  })

  it('blocks publishing until the required step is done, and reports it', async () => {
    api.get.mockResolvedValue(readiness(false))
    const onReadiness = renderGuide()

    expect(await screen.findByRole('button', { name: /Publish site/ })).toBeDisabled()
    expect(screen.getByText('0 of 1 required done')).toBeInTheDocument()
    await waitFor(() => expect(onReadiness).toHaveBeenCalledWith(false))
  })
})

describe('EditorHeader', () => {
  it('disables its Publish button while the checklist is blocking', () => {
    const { rerender } = render(<EditorHeader site={site} publicUrl="corner-bakery.gummfit.com" publishing={false} onPublish={vi.fn()} blocked />)
    expect(screen.getByRole('button', { name: /Publish/ })).toBeDisabled()

    rerender(<EditorHeader site={site} publicUrl="corner-bakery.gummfit.com" publishing={false} onPublish={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Publish/ })).toBeEnabled()
  })
})
