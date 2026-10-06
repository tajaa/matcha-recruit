import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TemplateGallery from './TemplateGallery'
import type { CappeTemplateSummary } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

const me = vi.hoisted(() => ({ account: { plan: 'free' } as { plan: string } }))
vi.mock('../hooks/useCappeMe', () => ({ useCappeMe: () => ({ account: me.account }) }))

const SWATCH = { bg: '#fff', surface: '#eee', brand: '#0a0', text: '#111' }
const MARGIN: CappeTemplateSummary = {
  slug: 'margin-blog', name: 'Margin', category: 'other', category_label: 'Other', tags: ['blog'],
  description: 'Writing first.', mode: 'light', heading_font: 'Fraunces', swatch: SWATCH,
  pages: [{ slug: 'home', title: 'Home' }, { slug: 'about', title: 'About' }],
}
const SAVEUR: CappeTemplateSummary = {
  slug: 'saveur-bistro', name: 'Saveur', category: 'food-drink', category_label: 'Food & Drink', tags: ['menu'],
  description: 'Menu and hours.', mode: 'dark', heading_font: 'Playfair Display', swatch: SWATCH,
  pages: [{ slug: 'home', title: 'Home' }, { slug: 'menu', title: 'Menu' }, { slug: 'visit', title: 'Visit' }],
}

function pickButtons() {
  return screen.getAllByRole('button', { name: /^Use the .* template$/ }).map((b) => b.getAttribute('aria-label'))
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  api.get.mockReset().mockResolvedValue([MARGIN, SAVEUR])
  me.account = { plan: 'free' }
})

describe('TemplateGallery', () => {
  it('shows the whole shelf with the chosen category first and badged', async () => {
    render(<TemplateGallery category="food-drink" busySlug={null} onPick={() => {}} />)

    expect(await screen.findAllByRole('button', { name: /^Use the/ })).toHaveLength(2)
    expect(pickButtons()).toEqual(['Use the Saveur template', 'Use the Margin template'])
    expect(screen.getAllByText('For you')).toHaveLength(1)
    expect(api.get).toHaveBeenCalledWith('/templates')
  })

  it('keeps the API order when no category is known', async () => {
    render(<TemplateGallery busySlug={null} onPick={() => {}} />)
    await screen.findAllByRole('button', { name: /^Use the/ })
    expect(pickButtons()).toEqual(['Use the Margin template', 'Use the Saveur template'])
    expect(screen.queryByText('For you')).not.toBeInTheDocument()
  })

  it('filters by category chip and comes back to everything', async () => {
    render(<TemplateGallery busySlug={null} onPick={() => {}} />)
    await screen.findAllByRole('button', { name: /^Use the/ })
    const chips = within(screen.getByRole('group', { name: 'Filter by category' }))

    fireEvent.click(chips.getByRole('button', { name: 'Other' }))
    expect(pickButtons()).toEqual(['Use the Margin template'])
    expect(chips.getByRole('button', { name: 'Other' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(chips.getByRole('button', { name: 'All' }))
    expect(pickButtons()).toHaveLength(2)
  })

  it('renders a free account the free layer in every preview', async () => {
    render(<TemplateGallery busySlug={null} onPick={() => {}} />)
    const frame = await screen.findByTitle('Saveur preview')
    expect(frame.getAttribute('src')).toContain('/templates/saveur-bistro/preview?page=home')
    expect(frame.getAttribute('src')).not.toContain('premium')
  })

  it('renders a paid account the premium polish it will keep', async () => {
    me.account = { plan: 'business' }
    render(<TemplateGallery busySlug={null} onPick={() => {}} />)
    const frame = await screen.findByTitle('Saveur preview')
    expect(frame.getAttribute('src')).toContain('premium=1')
  })

  it('opens a browsable full preview with a tab per page', async () => {
    const onPick = vi.fn()
    render(<TemplateGallery busySlug={null} onPick={onPick} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Preview the Saveur template' }))

    const dialog = screen.getByRole('dialog', { name: 'Saveur preview' })
    const frame = () => within(dialog).getByTitle(/^Saveur — /)
    expect(frame().getAttribute('src')).toContain('page=home')
    expect(within(dialog).getAllByRole('tab')).toHaveLength(3)

    fireEvent.click(within(dialog).getByRole('tab', { name: 'Menu' }))
    expect(frame().getAttribute('src')).toContain('page=menu')
    expect(within(dialog).getByRole('tab', { name: 'Menu' })).toHaveAttribute('aria-selected', 'true')

    // Links inside the frame can move it off the highlighted page without
    // telling us; clicking that highlighted tab must still reload the frame.
    const before = frame()
    fireEvent.click(within(dialog).getByRole('tab', { name: 'Menu' }))
    expect(frame()).not.toBe(before)
    expect(frame().getAttribute('src')).toContain('page=menu')

    // Choosing from inside the preview is the same pick as the card's button.
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use this template' }))
    expect(onPick).toHaveBeenCalledWith(SAVEUR)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Close preview' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes the preview on Escape', async () => {
    render(<TemplateGallery busySlug={null} onPick={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Preview the Margin template' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the busy spinner on the template being cloned and disables the rest', async () => {
    render(<TemplateGallery busySlug="margin-blog" onPick={() => {}} />)
    const picks = await screen.findAllByRole('button', { name: /^Use the/ })
    picks.forEach((b) => expect(b).toBeDisabled())
  })

  it('reports a failed catalog load', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    render(<TemplateGallery busySlug={null} onPick={() => {}} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('offline')
  })
})
