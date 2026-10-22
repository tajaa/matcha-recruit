import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import StockSearch from './StockSearch'
import LibraryPanel from './LibraryPanel'
import { licenseLabel } from './assets'
import type { CappeAsset, CappeStockImport, CappeStockResult } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const result = (over: Partial<CappeStockResult> = {}): CappeStockResult => ({
  source: 'openverse', source_id: 'r-1', title: 'Street fashion', creator: 'Giuseppe Milo', license: 'by',
  license_version: '2.0', license_url: '', provider_label: 'Flickr', landing_url: 'https://www.flickr.com/photos/x/1',
  credit_line: '“Street fashion” by Giuseppe Milo / CC BY 2.0 via Flickr', width: 1024, height: 683,
  thumb: '/public/stock-thumbs/tok1', imported: false, ...over,
})

const job = (over: Partial<CappeStockImport> = {}): CappeStockImport => ({
  id: 'i-1', source: 'openverse', source_id: 'r-1', status: 'pending', error: null, asset_id: null, asset: null,
  created_at: '2026-10-21T09:00:00Z', ...over,
})

const asset = (id: string): CappeAsset => ({
  id, kind: 'stock', url: `https://cdn.example.test/${id}.jpg`, prompt: null, aspect: null, image_size: null,
  created_at: '2026-10-21T09:00:00Z', source: 'openverse', source_url: null, title: 'Street fashion',
  creator: 'Giuseppe Milo', creator_url: null, license: 'by', license_version: '2.0', license_url: null,
  provider_label: 'Flickr', credit_line: `Credit for ${id}`, alt: null, caption: null, width: 1024, height: 683,
  bytes: 1, mime: 'image/jpeg', variants: {}, ai_generated: false, rights_attested_at: null,
  moderation: 'unchecked', updated_at: null,
})

const OPTIONS = { layouts: [], topics: [{ key: 'fashion', label: 'Fashion' }, { key: 'science', label: 'Science' }] }

function answer(routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path.includes(k))
    if (hit === undefined) return Promise.reject(new Error(`unexpected GET ${path}`))
    const value = routes[hit]
    return typeof value === 'function' ? (value as (p: string) => unknown)(path) : Promise.resolve(value)
  })
}

const searchFor = async (text: string) => {
  fireEvent.change(screen.getByPlaceholderText(/Harbour at dawn/), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
}

describe('licenseLabel', () => {
  it('names each license the way the badge prints it', () => {
    expect(licenseLabel('by', '2.0')).toBe('CC BY 2.0')
    expect(licenseLabel('by-sa', '4.0')).toBe('CC BY-SA 4.0')
    expect(licenseLabel('by-sa', '')).toBe('CC BY-SA')
    expect(licenseLabel('cc0')).toBe('CC0')
    expect(licenseLabel('pdm')).toBe('Public domain')
    expect(licenseLabel(null)).toBe('')
  })
})

describe('StockSearch', () => {
  it('searches the chosen archive and shows each picture with its license and credit', async () => {
    answer({
      '/stories/options': OPTIONS,
      '/library/search': { source: 'openverse', query: 'street fashion', page: 0, has_more: true,
        results: [result(), result({ source_id: 'r-2', imported: true, license: 'cc0', license_version: '' })] },
    })
    render(<StockSearch siteId="s-1" onImported={vi.fn()} />)
    await searchFor(' street fashion ')
    const list = await screen.findByRole('list', { name: 'Results' })
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/library/search?source=openverse&q=street+fashion&page=0')
    expect(within(list).getByText('CC BY 2.0')).toBeInTheDocument()
    expect(within(list).getByText('CC0')).toBeInTheDocument()
    expect(within(list).getAllByText(/by Giuseppe Milo \/ CC BY 2.0 via Flickr/)).toHaveLength(2)
    expect(within(list).getAllByRole('img')[0]).toHaveAttribute('src', '/api/cappe/public/stock-thumbs/tok1')
    expect(within(list).getByText('In library')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Pick Street/ })[1]).toBeDisabled()

    fireEvent.click(screen.getByRole('tab', { name: 'NASA' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      '/sites/s-1/library/search?source=nasa&q=street+fashion&page=0'))
  })

  it('loads more and says when an archive has nothing', async () => {
    answer({
      '/stories/options': OPTIONS,
      'page=0': { source: 'openverse', query: 'harbor', page: 0, has_more: true, results: [result()] },
      'page=1': { source: 'openverse', query: 'harbor', page: 1, has_more: false, results: [result({ source_id: 'r-9' })] },
    })
    render(<StockSearch siteId="s-1" onImported={vi.fn()} />)
    await searchFor('harbor')
    fireEvent.click(await screen.findByRole('button', { name: 'More from Openverse' }))
    await waitFor(() => expect(screen.getAllByRole('button', { name: /^Pick Street/ })).toHaveLength(2))
    expect(screen.queryByRole('button', { name: /More from/ })).not.toBeInTheDocument()

    answer({ '/stories/options': OPTIONS,
      '/library/search': { source: 'openverse', query: 'zzz', page: 0, has_more: false, results: [] } })
    await searchFor('zzz')
    expect(await screen.findByText(/Nothing we can publish for “zzz”/)).toBeInTheDocument()
  })

  it('offers more when a page had nothing publishable but the archive has more', async () => {
    answer({ '/stories/options': OPTIONS,
      '/library/search': { source: 'met', query: 'harbor', page: 0, has_more: true, results: [] } })
    render(<StockSearch siteId="s-1" onImported={vi.fn()} />)
    await searchFor('harbor')
    expect(await screen.findByRole('button', { name: /More from/ })).toBeInTheDocument()
  })

  it('hands over a picture imported again on the same import', async () => {
    // Deleted from the library and imported again: the server revives the
    // same import row, with a new library picture.
    let landed = asset('a-7')
    answer({ '/stories/options': OPTIONS, '/library/imports': () => Promise.resolve({
      imports: [job({ status: 'ready', asset: landed })] }) })
    api.post.mockResolvedValue({ imports: [job()], remaining_today: 10 })
    const onImported = vi.fn()
    render(<StockSearch siteId="s-1" onImported={onImported} pollMs={5} />)
    fireEvent.change(await screen.findByLabelText('Topic to stock'), { target: { value: 'science' } })
    fireEvent.click(screen.getByRole('button', { name: /Add 12 pictures/ }))
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(asset('a-7')))
    landed = asset('a-8')
    await waitFor(() => expect(screen.getByRole('button', { name: /Add 12 pictures/ })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: /Add 12 pictures/ }))
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(asset('a-8')))
  })

  it('shows a search the archive refused', async () => {
    answer({ '/stories/options': OPTIONS, '/library/search': () => Promise.reject(new Error('That archive didn’t answer.')) })
    render(<StockSearch siteId="s-1" onImported={vi.fn()} />)
    await searchFor('x')
    expect(await screen.findByRole('alert')).toHaveTextContent('That archive didn’t answer.')
  })

  it('imports the picked pictures and hands each over as it lands', async () => {
    const onImported = vi.fn()
    let polls = 0
    answer({
      '/stories/options': OPTIONS,
      '/library/search': { source: 'openverse', query: 'x', page: 0, has_more: false,
        results: [result(), result({ source_id: 'r-2' })] },
      '/library/imports': () => {
        polls += 1
        return Promise.resolve({ imports: polls === 1
          ? [job({ status: 'working' }), job({ id: 'i-2', source_id: 'r-2', status: 'refused',
            error: 'This picture isn’t offered under a license we can publish any more.' })]
          : [job({ status: 'ready', asset_id: 'a-1', asset: asset('a-1') })] })
      },
    })
    api.post.mockResolvedValue({ imports: [job(), job({ id: 'i-2', source_id: 'r-2' })], remaining_today: 298 })
    render(<StockSearch siteId="s-1" postId="p-1" onImported={onImported} pollMs={5} />)
    await searchFor('x')
    const picks = await screen.findAllByRole('button', { name: /^Pick Street/ })
    fireEvent.click(picks[0])
    fireEvent.click(picks[1])
    fireEvent.click(screen.getByRole('button', { name: 'Import 2 pictures' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/library/import', {
      items: [{ source: 'openverse', source_id: 'r-1' }, { source: 'openverse', source_id: 'r-2' }], post_id: 'p-1',
    }))
    expect(await screen.findByText('You can import 298 more today.')).toBeInTheDocument()
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(asset('a-1')))
    expect(onImported).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('1 of 2 in your library.')).toBeInTheDocument()
    expect(screen.getByText(/isn’t offered under a license we can publish/)).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/library/imports?ids=i-1,i-2')
    await new Promise((r) => setTimeout(r, 30))
    expect(polls).toBe(2) // nothing left waiting: polling stopped
  })

  it('says how many are left when the day is used up', async () => {
    answer({ '/stories/options': OPTIONS,
      '/library/search': { source: 'met', query: 'x', page: 0, has_more: false, results: [result({ source: 'met' })] } })
    api.post.mockRejectedValue(new Error('You can import 0 more pictures today (your plan allows 25 a day).'))
    render(<StockSearch siteId="s-1" onImported={vi.fn()} />)
    await searchFor('x')
    fireEvent.click(await screen.findByRole('button', { name: /^Pick Street/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Import 1 picture' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('your plan allows 25 a day')
  })

  it('stocks a topic', async () => {
    answer({ '/stories/options': OPTIONS, '/library/imports': { imports: [job({ status: 'ready', asset: asset('a-7') })] } })
    api.post.mockResolvedValue({ imports: [job()], remaining_today: 10 })
    const onImported = vi.fn()
    render(<StockSearch siteId="s-1" onImported={onImported} pollMs={5} />)
    const button = await screen.findByRole('button', { name: /Add 12 pictures/ })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Topic to stock'), { target: { value: 'science' } })
    fireEvent.click(button)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/library/stock-topic',
      { topic: 'science', count: 12 }))
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(asset('a-7')))
  })
})

describe('LibraryPanel with free photos', () => {
  it('opens the archive search and puts imports at the top of the library', async () => {
    answer({
      '/assets': { assets: [asset('a-0')] },
      '/stories/options': OPTIONS,
      '/library/search': { source: 'openverse', query: 'x', page: 0, has_more: false, results: [result()] },
      '/library/imports': { imports: [job({ status: 'ready', asset: asset('a-9') })] },
    })
    api.post.mockResolvedValue({ imports: [job()], remaining_today: 5 })
    render(<LibraryPanel siteId="s-1" />)
    expect(await screen.findByText('Credit for a-0')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Find free photos/ }))
    expect(screen.getByRole('region', { name: 'Find free photos' })).toBeInTheDocument()
    await searchFor('x')
    fireEvent.click(await screen.findByRole('button', { name: /^Pick Street/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Import 1 picture' }))
    expect(await screen.findByText('Credit for a-9', {}, { timeout: 4000 })).toBeInTheDocument()
    const credits = screen.getAllByText(/^Credit for a-/).map((n) => n.textContent)
    expect(credits).toEqual(['Credit for a-9', 'Credit for a-0'])
  })
})
