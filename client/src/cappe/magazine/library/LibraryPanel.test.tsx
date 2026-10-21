import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LibraryPanel from './LibraryPanel'
import { creditEditable, thumbUrl } from './assets'
import type { CappeAsset } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const asset = (over: Partial<CappeAsset> = {}): CappeAsset => ({
  id: 'a-1', kind: 'upload', url: 'https://cdn.example.test/a.jpg', prompt: null, aspect: null,
  image_size: null, created_at: '2026-10-20T12:00:00Z', source: 'upload', source_url: null, title: null,
  creator: null, creator_url: null, license: 'own', license_version: null, license_url: null,
  provider_label: null, credit_line: 'Photo: Ana Ruiz', alt: 'Boats at dawn', caption: null, width: 1200,
  height: 800, bytes: 1000, mime: 'image/jpeg', variants: {}, ai_generated: false, rights_attested_at: null,
  moderation: 'unchecked', updated_at: null, ...over,
})

describe('LibraryPanel helpers', () => {
  it('shows the smallest stored size as the thumbnail', () => {
    expect(thumbUrl(asset())).toBe('https://cdn.example.test/a.jpg')
    expect(thumbUrl(asset({ variants: { webp: [{ w: 480, url: 'https://cdn.example.test/w480.webp' }] } })))
      .toBe('https://cdn.example.test/w480.webp')
  })

  it('lets the owner write the credit only on their own non-AI uploads', () => {
    expect(creditEditable(asset())).toBe(true)
    expect(creditEditable(asset({ kind: 'stock' }))).toBe(false)
    expect(creditEditable(asset({ ai_generated: true }))).toBe(false)
  })
})

describe('LibraryPanel', () => {
  it('lists pictures with their credit and an AI badge', async () => {
    api.get.mockResolvedValue({ assets: [
      asset(),
      asset({ id: 'a-2', kind: 'generated', ai_generated: true, credit_line: 'AI illustration', alt: 'A lighthouse' }),
    ] })
    render(<LibraryPanel siteId="s-1" />)
    expect(await screen.findByText('Photo: Ana Ruiz')).toBeInTheDocument()
    expect(screen.getByText('AI illustration')).toBeInTheDocument()
    expect(screen.getAllByText('AI')).toHaveLength(2) // the AI tab and the badge
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/assets')
  })

  it('filters by kind and searches after typing settles', async () => {
    api.get.mockResolvedValue({ assets: [] })
    render(<LibraryPanel siteId="s-1" />)
    await screen.findByText(/No pictures yet/)
    fireEvent.click(screen.getByRole('tab', { name: 'Archive' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/assets?kind=stock'))
    vi.useFakeTimers()
    fireEvent.change(screen.getByPlaceholderText(/Search alt text/), { target: { value: ' harbour ' } })
    await act(async () => { vi.advanceTimersByTime(350) })
    vi.useRealTimers()
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/assets?kind=stock&q=harbour'))
    expect(await screen.findByText('Nothing matches.')).toBeInTheDocument()
  })

  it('shows a load failure', async () => {
    api.get.mockRejectedValue(new Error('Server error'))
    render(<LibraryPanel siteId="s-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
  })

  it('needs the permission box before a picture can be added, then sends what is printed beside it', async () => {
    api.get.mockResolvedValue({ assets: [] })
    api.upload.mockResolvedValue(asset({ id: 'new', alt: 'Market', credit_line: 'Photo: me' }))
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /Upload a picture/ }))
    const form = screen.getByRole('form', { name: 'Upload a picture' })
    const file = new File(['x'], 'market.jpg', { type: 'image/jpeg' })
    fireEvent.change(form.querySelector('input[type=file]') as HTMLInputElement, { target: { files: [file] } })
    fireEvent.change(screen.getByPlaceholderText(/What's in the picture/), { target: { value: 'Market' } })
    fireEvent.change(screen.getAllByPlaceholderText('Photo: your name')[0], { target: { value: 'Photo: me' } })
    const submit = screen.getByRole('button', { name: /Add to library/ })
    expect(submit).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/I took this picture/))
    fireEvent.click(submit)

    await waitFor(() => expect(api.upload).toHaveBeenCalled())
    const [path, sent] = api.upload.mock.calls[0] as [string, FormData]
    expect(path).toBe('/sites/s-1/assets/upload')
    expect(sent.get('rights_attested')).toBe('true')
    expect(sent.get('ai_made')).toBe('false')
    expect(sent.get('alt')).toBe('Market')
    expect(sent.get('credit_line')).toBe('Photo: me')
    // the new picture opens in the details panel
    expect(await screen.findByRole('complementary', { name: 'Picture details' })).toBeInTheDocument()
  })

  it('sends no credit for an AI-made picture', async () => {
    api.get.mockResolvedValue({ assets: [] })
    api.upload.mockResolvedValue(asset({ id: 'new', ai_generated: true, credit_line: 'AI illustration' }))
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /Upload a picture/ }))
    const form = screen.getByRole('form', { name: 'Upload a picture' })
    fireEvent.change(form.querySelector('input[type=file]') as HTMLInputElement,
      { target: { files: [new File(['x'], 'art.png', { type: 'image/png' })] } })
    fireEvent.change(screen.getAllByPlaceholderText('Photo: your name')[0], { target: { value: 'Photo: me' } })
    fireEvent.click(screen.getByLabelText(/made with AI/))
    expect(screen.getByDisplayValue('AI illustration')).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/I took this picture/))
    fireEvent.click(screen.getByRole('button', { name: /Add to library/ }))
    await waitFor(() => expect(api.upload).toHaveBeenCalled())
    const sent = api.upload.mock.calls[0][1] as FormData
    expect(sent.get('ai_made')).toBe('true')
    expect(sent.get('credit_line')).toBeNull()
  })

  it('shows an upload failure', async () => {
    api.get.mockResolvedValue({ assets: [] })
    api.upload.mockRejectedValue(new Error('Image too large (max 15 MB)'))
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /Upload a picture/ }))
    const form = screen.getByRole('form', { name: 'Upload a picture' })
    fireEvent.change(form.querySelector('input[type=file]') as HTMLInputElement,
      { target: { files: [new File(['x'], 'big.jpg', { type: 'image/jpeg' })] } })
    fireEvent.click(screen.getByLabelText(/I took this picture/))
    fireEvent.click(screen.getByRole('button', { name: /Add to library/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('max 15 MB')
  })

  it('edits alt text and the credit of an upload', async () => {
    api.get.mockResolvedValue({ assets: [asset()] })
    api.patch.mockResolvedValue(asset({ alt: 'Fishing boats', credit_line: 'Photo: A. Ruiz' }))
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /Photo: Ana Ruiz/ }))
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByDisplayValue('Boats at dawn'), { target: { value: 'Fishing boats' } })
    fireEvent.change(screen.getByDisplayValue('Photo: Ana Ruiz'), { target: { value: 'Photo: A. Ruiz' } })
    fireEvent.click(save)
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/sites/s-1/assets/a-1',
      { alt: 'Fishing boats', caption: '', credit_line: 'Photo: A. Ruiz' }))
    expect(await screen.findByRole('button', { name: /Photo: A. Ruiz/ })).toBeInTheDocument()
  })

  it('prints an archive picture\'s credit as is and links to where it came from', async () => {
    api.get.mockResolvedValue({ assets: [asset({
      kind: 'stock', credit_line: 'Photo: Jo / CC BY 2.0 via Flickr', source_url: 'https://www.flickr.com/photos/x',
    })] })
    api.patch.mockResolvedValue(asset({ kind: 'stock', alt: 'Harbour' }))
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /CC BY 2.0/ }))
    expect(screen.getByText(/comes from the picture's license/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Where it came from/ })).toHaveAttribute('href', 'https://www.flickr.com/photos/x')
    expect(screen.queryByPlaceholderText('Photo: your name')).not.toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('Boats at dawn'), { target: { value: 'Harbour' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/sites/s-1/assets/a-1', { alt: 'Harbour', caption: '' }))
  })

  it('says an AI picture is always credited as AI', async () => {
    api.get.mockResolvedValue({ assets: [asset({ kind: 'generated', ai_generated: true, credit_line: 'AI illustration' })] })
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /AI illustration/ }))
    expect(screen.getByText('AI pictures are always credited as AI.')).toBeInTheDocument()
  })

  it('shows a save failure', async () => {
    api.get.mockResolvedValue({ assets: [asset()] })
    api.patch.mockRejectedValue(new Error('This picture\'s credit comes from its source'))
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /Photo: Ana Ruiz/ }))
    fireEvent.change(screen.getByDisplayValue('Boats at dawn'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('comes from its source')
  })

  it('removes a picture after confirming, and offers it to a picker', async () => {
    api.get.mockResolvedValue({ assets: [asset()] })
    api.delete.mockResolvedValue(undefined)
    const onPick = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<LibraryPanel siteId="s-1" onPick={onPick} />)
    fireEvent.click(await screen.findByRole('button', { name: /Photo: Ana Ruiz/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use this picture' }))
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 'a-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove from library' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/sites/s-1/assets/a-1'))
    expect(await screen.findByText(/No pictures yet/)).toBeInTheDocument()
  })

  it('keeps a picture when removing it fails or is cancelled', async () => {
    api.get.mockResolvedValue({ assets: [asset()] })
    api.delete.mockRejectedValue(new Error('Asset not found'))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<LibraryPanel siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: /Photo: Ana Ruiz/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove from library' }))
    expect(api.delete).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Remove from library' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Asset not found')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })
})
