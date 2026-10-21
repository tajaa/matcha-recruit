import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AssistPanel from './editor/AssistPanel'
import { textPreview, withCaption, withText } from './editor/blocks'
import IllustrateForm from './library/IllustrateForm'
import type { CappeAsset, StoryBlock } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() }))
vi.mock('../api', async () => {
  const real = await vi.importActual<typeof import('../api')>('../api')
  return { cappeApi: api, cappeApiBase: '/api/cappe', CappeApiError: real.CappeApiError }
})
const { CappeApiError } = await vi.importActual<typeof import('../api')>('../api')

const asset = (id: string, over: Partial<CappeAsset> = {}): CappeAsset => ({
  id, kind: 'stock', url: `https://cdn.example.test/${id}.jpg`, prompt: null, aspect: null, image_size: null,
  created_at: '2026-10-21T09:00:00Z', source: 'openverse', source_url: null, title: 'Harbour', creator: 'Ana',
  creator_url: null, license: 'by', license_version: '2.0', license_url: null, provider_label: 'Flickr',
  credit_line: '“Harbour” by Ana / CC BY 2.0 via Flickr', alt: null, caption: null, width: 1600, height: 1000,
  bytes: 1, mime: 'image/jpeg', variants: {}, ai_generated: false, rights_attested_at: null, moderation: 'unchecked',
  updated_at: null, ...over,
})

const BLOCKS: StoryBlock[] = [
  { type: 'cover', asset_id: 'a-1', style: 'overlay', tone: 'light', focal: { x: 50, y: 50 } },
  { type: 'text', md: 'The harbour wakes before the town does. **Boats** go out at four in the morning.', dropcap: true, columns: 1 },
  { type: 'photo', asset_id: 'a-2', caption: '', size: 'wide' },
  { type: 'photos', layout: 'pair', items: [{ asset_id: 'a-2', caption: '' }, { asset_id: 'a-1', caption: 'x' }] },
]

describe('block helpers', () => {
  it('captions every use of a picture and replaces only a text block', () => {
    const next = withCaption(BLOCKS, 'a-2', 'The first boat out.')
    expect(next[2]).toMatchObject({ caption: 'The first boat out.' })
    expect(next[3]).toMatchObject({ items: [{ asset_id: 'a-2', caption: 'The first boat out.' }, { asset_id: 'a-1', caption: 'x' }] })
    expect(next[0]).toBe(BLOCKS[0])
    expect(withText(BLOCKS, 1, 'Shorter.')[1]).toMatchObject({ md: 'Shorter.' })
    expect(withText(BLOCKS, 2, 'Shorter.')[2]).toBe(BLOCKS[2])
    expect(textPreview('The harbour wakes before the **town** does at four', 5)).toBe('The harbour wakes before the…')
  })
})

describe('IllustrateForm', () => {
  it('draws an illustration and hands it to the library', async () => {
    const onDone = vi.fn()
    api.post.mockResolvedValue(asset('g-1', { kind: 'generated', ai_generated: true, credit_line: 'AI illustration' }))
    render(<IllustrateForm siteId="s-1" onDone={onDone} onCancel={vi.fn()} />)
    const button = screen.getByRole('button', { name: /Illustrate/ })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/lighthouse keeper/), { target: { value: ' A kitchen at night ' } })
    fireEvent.change(screen.getByLabelText('Shape'), { target: { value: '9:16' } })
    fireEvent.click(button)
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/library/illustrate', { prompt: 'A kitchen at night', aspect: '9:16' })
    expect(screen.getByText(/always credited “AI illustration”/)).toBeInTheDocument()
  })

  it('shows a refusal as a refusal, and other failures as errors', async () => {
    api.post.mockRejectedValueOnce(new CappeApiError('AI illustrations can’t show real people.', 'real_person', 422))
    render(<IllustrateForm siteId="s-1" onDone={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText(/lighthouse keeper/), { target: { value: 'Senator Warren at a rally' } })
    fireEvent.click(screen.getByRole('button', { name: /Illustrate/ }))
    expect(await screen.findByRole('alert')).toHaveClass('text-amber-300')
    expect(screen.getByRole('alert')).toHaveTextContent('can’t show real people')
    api.post.mockRejectedValueOnce(new CappeApiError('Illustrations aren’t available right now.', undefined, 503))
    fireEvent.click(screen.getByRole('button', { name: /Illustrate/ }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveClass('text-red-400'))
  })
})

function panel(over: Partial<Parameters<typeof AssistPanel>[0]> = {}) {
  const props = {
    siteId: 's-1', postId: 'p-1', title: 'Before the town wakes', excerpt: 'A morning at the harbour.', blocks: BLOCKS,
    assets: new Map([['a-1', asset('a-1')], ['a-2', asset('a-2', { alt: 'Already described' })]]),
    onHeadline: vi.fn(), onCaption: vi.fn(), onAlt: vi.fn(), onTighten: vi.fn(), onDraft: vi.fn(), onFind: vi.fn(),
    onClose: vi.fn(), ...over,
  }
  render(<AssistPanel {...props} />)
  return props
}

describe('AssistPanel', () => {
  it('sends the editor’s unsaved story and applies a headline', async () => {
    api.post.mockResolvedValue({ action: 'headlines', headlines: [{ title: 'Four a.m.', dek: 'Boats go out.', kicker: 'Dispatch' }] })
    const props = panel()
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    const list = await screen.findByRole('list', { name: 'Headlines' })
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/posts/p-1/assist', {
      action: 'headlines', content: { blocks: BLOCKS }, title: 'Before the town wakes', excerpt: 'A morning at the harbour.',
    })
    fireEvent.click(within(list).getByRole('button', { name: 'Use this' }))
    expect(props.onHeadline).toHaveBeenCalledWith({ title: 'Four a.m.', dek: 'Boats go out.', kicker: 'Dispatch' })
    expect(within(list).getByText('Used')).toBeInTheDocument()
  })

  it('applies captions, and alt text only where a picture has none', async () => {
    api.post.mockResolvedValue({ action: 'captions', captions: [
      { asset_id: 'a-1', caption: 'The harbour at dusk.', alt: 'Boats moored at dusk' },
      { asset_id: 'a-2', caption: 'The first boat out.', alt: 'A boat leaving' },
    ] })
    api.patch.mockResolvedValue(asset('a-1', { alt: 'Boats moored at dusk' }))
    const props = panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Captions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    const list = await screen.findByRole('list', { name: 'Captions' })
    const [first, second] = within(list).getAllByRole('button', { name: 'Use this' })
    fireEvent.click(first)
    await waitFor(() => expect(props.onAlt).toHaveBeenCalledWith(asset('a-1', { alt: 'Boats moored at dusk' })))
    expect(props.onCaption).toHaveBeenCalledWith('a-1', 'The harbour at dusk.')
    expect(api.patch).toHaveBeenCalledWith('/sites/s-1/assets/a-1', { alt: 'Boats moored at dusk' })
    fireEvent.click(second)
    await waitFor(() => expect(props.onCaption).toHaveBeenCalledWith('a-2', 'The first boat out.'))
    expect(api.patch).toHaveBeenCalledTimes(1) // a-2 keeps the alt text it has
  })

  it('tightens a chosen passage with a before and after', async () => {
    api.post.mockResolvedValue({ action: 'tighten', md: 'Boats go out at four.', block: 1 })
    const props = panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Tighten' }))
    expect(screen.getByLabelText('Passage')).toHaveDisplayValue(/Block 2: The harbour wakes/)
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Tighter')).toBeInTheDocument()
    expect(api.post.mock.calls[0][1]).toMatchObject({ action: 'tighten', block: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'Replace the passage' }))
    expect(props.onTighten).toHaveBeenCalledWith(1, 'Boats go out at four.')
  })

  it('drafts from notes, warns about facts to check, and asks before replacing words', async () => {
    const draft = { title: 'Four a.m.', excerpt: 'Dawn.', kicker: 'Dispatch', content: { blocks: [
      { type: 'text', md: 'Boats go out at four. [check: how many boats]', dropcap: true, columns: 1 },
    ] } }
    api.post.mockResolvedValue({ action: 'draft', draft })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const props = panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Draft' }))
    fireEvent.change(screen.getByLabelText('Your notes'), { target: { value: 'Out with the boats at 4am' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(/Fill in each \[check: …\]/)).toBeInTheDocument()
    expect(api.post.mock.calls[0][1]).toMatchObject({ action: 'draft', notes: 'Out with the boats at 4am' })
    fireEvent.click(screen.getByRole('button', { name: 'Use this draft' }))
    expect(confirm).toHaveBeenCalled()
    expect(props.onDraft).toHaveBeenCalledWith(draft)
  })

  it('suggests archive searches and opens one', async () => {
    api.post.mockResolvedValue({ action: 'search_terms', terms: [{ source: 'nasa', query: 'earth at night' }] })
    const props = panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Find pictures' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    const list = await screen.findByRole('list', { name: 'Searches' })
    expect(within(list).getByText('NASA')).toBeInTheDocument()
    fireEvent.click(within(list).getByRole('button', { name: /Search/ }))
    expect(props.onFind).toHaveBeenCalledWith({ source: 'nasa', query: 'earth at night' })
  })

  it('shows what went wrong', async () => {
    api.post.mockRejectedValue(new Error('Writing help isn’t available right now.'))
    panel()
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t available')
  })
})
