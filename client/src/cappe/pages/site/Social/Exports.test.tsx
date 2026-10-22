import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Exports from './Exports'
import type { CappeSocialExport, CappeSocialSettings } from '../../../types'

const api = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(),
}))
vi.mock('../../../api', () => ({ cappeApi: api }))
const upload = vi.hoisted(() => vi.fn())
vi.mock('../../../utils/socialVideo', async (orig) => ({
  ...(await orig<typeof import('../../../utils/socialVideo')>()), uploadVideo: upload,
}))

const SETTINGS: CappeSocialSettings = {
  autoreply_mode: 'off', reply_to_comments: true, reply_to_messages: true, tone: 'friendly', business_facts: '',
  signature: null, default_hashtags: [], max_auto_per_hour: 20, escalate_words: [], autoreply_available: true,
  video_available: true, ai_available: true,
}
const FILE = { url: 'https://cdn.example.test/v.mp4', width: 1080, height: 1920, duration_ms: 42_000, bytes: 9, trimmed: false, error: null }
const READY: CappeSocialExport = {
  id: 'e1', asset_id: 'a1', status: 'ready', platforms: ['instagram', 'tiktok', 'youtube'], captions: true,
  files: { instagram: FILE, tiktok: FILE, youtube: { ...FILE, width: 1920, height: 1080, trimmed: true } },
  progress: { done: 2, total: 2, step: null }, srt: true,
  texts: {
    instagram: { text: 'Oat lattes are back.\n\n#oatlatte', link: 'https://po.example.test/?utm_source=instagram' },
    tiktok: { text: 'POV: oat latte szn #fyp', link: null },
    youtube: { title: 'Oat lattes are back', description: 'Back for fall.', tags: ['oat latte', 'coffee'] },
  },
  warnings: [], error: null, filename: 'latte.mov', poster: 'https://cdn.example.test/p.jpg', duration_ms: 42_000,
  original: true, created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z',
}
const WORKING: CappeSocialExport = {
  ...READY, id: 'e2', status: 'working', files: { tiktok: null }, platforms: ['tiktok'], srt: false, texts: {},
  progress: { done: 0, total: 1, step: 'transcribe' }, warnings: ['That video has no sound, so there are no captions.'],
}

function show(settings = SETTINGS) {
  const onCount = vi.fn()
  render(<Exports siteId="s-1" settings={settings} refreshKey={0} onCount={onCount} />)
  return onCount
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
  upload.mockReset()
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('Exports', () => {
  it('lists each file with its download and the words to paste', async () => {
    api.get.mockResolvedValueOnce([READY])
    const onCount = show()
    const card = await screen.findByRole('region', { name: 'latte.mov' })
    expect(onCount).toHaveBeenCalledWith(1)
    expect(within(card).getByText('Ready')).toBeInTheDocument()
    expect(within(card).getByText('1920×1080 · 0:42 · first 3 minutes')).toBeInTheDocument()
    expect(within(card).getByText('Captions (.srt)')).toBeInTheDocument()
    expect(within(card).getByText(/POV: oat latte szn/)).toBeInTheDocument()
    expect(within(card).getByText('oat latte, coffee')).toBeInTheDocument()
    expect(within(card).getByText(/Link for your bio/)).toBeInTheDocument()

    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    api.get.mockResolvedValueOnce({ url: 'https://dl.test/tiktok', filename: 'po-latte-tiktok.mp4', expires_in: 600 })
    fireEvent.click(within(card).getByRole('button', { name: 'Download TikTok' }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://dl.test/tiktok'))
    expect(api.get).toHaveBeenLastCalledWith('/sites/s-1/social/exports/e1/download?target=tiktok')

    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    fireEvent.click(within(card).getByRole('button', { name: 'Copy YouTube title' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('Oat lattes are back'))
    expect(await within(card).findByText('Copied')).toBeInTheDocument()
  })

  it('shows progress while a file is being made, and checks back', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    api.get.mockResolvedValueOnce([WORKING]).mockResolvedValueOnce([{ ...WORKING, status: 'ready', files: { tiktok: FILE } }])
    show()
    const card = await screen.findByRole('region', { name: 'latte.mov' })
    expect(within(card).getByText(/Listening for the words · 0 of 1 files/)).toBeInTheDocument()
    expect(within(card).getByText('That video has no sound, so there are no captions.')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Download TikTok' })).toBeDisabled()
    expect(within(card).getByText('Being made…')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(await within(card).findByText('Ready')).toBeInTheDocument()
  })

  it('prepares a dropped video for the platforms picked', async () => {
    api.get.mockResolvedValueOnce([])
    show()
    expect(await screen.findByText(/No files yet/)).toBeInTheDocument()
    upload.mockImplementation(async (_site: string, _file: File, progress: (n: number) => void) => {
      progress(50)
      return { id: 'a9', status: 'rendering' }
    })
    api.post.mockResolvedValueOnce({ ...WORKING, id: 'e9', filename: 'new.mp4' })
    fireEvent.click(screen.getByRole('button', { name: 'YouTube' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Burn in word-for-word captions' }))
    const clip = new File([new Uint8Array(4)], 'new.mp4', { type: 'video/mp4' })
    fireEvent.change(screen.getByLabelText('Video to prepare'), { target: { files: [clip] } })
    expect(await screen.findByRole('region', { name: 'new.mp4' })).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/social/exports', {
      asset_id: 'a9', platforms: ['instagram', 'tiktok'], captions: true })
  })

  it('refuses what it can’t prepare and says why', async () => {
    api.get.mockResolvedValueOnce([])
    show()
    await screen.findByText(/No files yet/)
    fireEvent.change(screen.getByLabelText('Video to prepare'), {
      target: { files: [new File(['x'], 'a.avi', { type: 'video/x-msvideo' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Videos must be MP4, MOV or WebM')
    for (const name of ['Instagram', 'TikTok', 'YouTube']) fireEvent.click(screen.getByRole('button', { name }))
    fireEvent.change(screen.getByLabelText('Video to prepare'), {
      target: { files: [new File([new Uint8Array(4)], 'b.mp4', { type: 'video/mp4' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Pick at least one platform')
    fireEvent.click(screen.getByRole('button', { name: 'TikTok' }))
    upload.mockResolvedValueOnce({ id: 'a1', status: 'failed', error: 'No video in it' })
    fireEvent.change(screen.getByLabelText('Video to prepare'), {
      target: { files: [new File([new Uint8Array(4)], 'c.mp4', { type: 'video/mp4' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('No video in it')
  })

  it('deletes an export and reports failures', async () => {
    api.get.mockResolvedValueOnce([READY])
    show()
    const card = await screen.findByRole('region', { name: 'latte.mov' })
    api.get.mockRejectedValueOnce(new Error('That file isn’t ready yet'))
    fireEvent.click(within(card).getByRole('button', { name: 'Download Original' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That file isn’t ready yet')
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
    fireEvent.click(within(card).getByRole('button', { name: 'Copy Instagram caption' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t copy')
    api.delete.mockResolvedValueOnce(undefined)
    fireEvent.click(within(card).getByRole('button', { name: 'Delete these files' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'latte.mov' })).not.toBeInTheDocument())
    expect(api.delete).toHaveBeenCalledWith('/sites/s-1/social/exports/e1')
  })

  it('explains the plan gate and a failed load', async () => {
    api.get.mockRejectedValueOnce(new Error('Social posting isn’t included in your plan.'))
    show({ ...SETTINGS, video_available: false })
    expect(screen.getByText(/Video is part of the Business, Pro and Creator plans/)).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Social posting isn’t included in your plan.')
  })
})
