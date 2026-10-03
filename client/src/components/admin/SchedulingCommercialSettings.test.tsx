import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SchedulingCommercialSettings } from './SchedulingCommercialSettings'
import { landingMedia } from '../../api/admin/landingMedia'
import { EMPTY_COMMERCIAL } from '../../types/landingMedia'
vi.mock('../../api/admin/landingMedia', () => ({ landingMedia: { getAdmin: vi.fn(), uploadCommercial: vi.fn(), saveCommercial: vi.fn() } }))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(landingMedia.getAdmin).mockResolvedValue({ hero_video_url: null, hero_poster_url: null, sizzle_videos: [], customer_logos: [], testimonials: [], scheduling_commercial: EMPTY_COMMERCIAL })
})

describe('commercial admin', () => {
  it('uploads before enabling, then saves separately from the legacy form', async () => {
    const url = 'https://media.example.com/film.mp4'
    vi.mocked(landingMedia.uploadCommercial).mockResolvedValue(url)
    vi.mocked(landingMedia.saveCommercial).mockImplementation(async (data) => ({ ok: true, value: data }))
    render(<SchedulingCommercialSettings />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save commercial' }).hasAttribute('disabled')).toBe(false))
    expect(screen.getByRole('checkbox').hasAttribute('disabled')).toBe(true)
    fireEvent.change(screen.getByLabelText('Upload desktop commercial'), { target: { files: [new File(['video'], 'film.mp4', { type: 'video/mp4' })] } })
    await waitFor(() => expect(screen.getByRole('checkbox').hasAttribute('disabled')).toBe(false))
    expect(landingMedia.uploadCommercial).toHaveBeenCalledWith(expect.any(File), 'desktop_video', expect.any(Function))
    expect(landingMedia.saveCommercial).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Save commercial' }))
    await waitFor(() => expect(landingMedia.saveCommercial).toHaveBeenCalledWith({ ...EMPTY_COMMERCIAL, desktop_video_url: url, enabled: true }))
    expect(await screen.findByRole('status')).toBeTruthy()
  })
  it('keeps save disabled if settings fail to load', async () => {
    vi.mocked(landingMedia.getAdmin).mockRejectedValue(new Error('offline'))
    render(<SchedulingCommercialSettings />)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Save commercial' }).hasAttribute('disabled')).toBe(true)
  })
  it('retains the prior commercial after a failed replacement', async () => {
    const url = 'https://media.example.com/prior.mp4'
    vi.mocked(landingMedia.getAdmin).mockResolvedValue({ hero_video_url: null, hero_poster_url: null, sizzle_videos: [], customer_logos: [], testimonials: [], scheduling_commercial: { ...EMPTY_COMMERCIAL, enabled: true, desktop_video_url: url } })
    vi.mocked(landingMedia.uploadCommercial).mockRejectedValue(new Error('Upload failed'))
    vi.mocked(landingMedia.saveCommercial).mockImplementation(async (data) => ({ ok: true, value: data }))
    render(<SchedulingCommercialSettings />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save commercial' }).hasAttribute('disabled')).toBe(false))
    fireEvent.change(screen.getByLabelText('Upload desktop commercial'), { target: { files: [new File(['video'], 'replacement.mp4', { type: 'video/mp4' })] } })
    expect(await screen.findByRole('alert')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save commercial' }))
    await waitFor(() => expect(landingMedia.saveCommercial).toHaveBeenCalledWith(expect.objectContaining({ enabled: true, desktop_video_url: url })))
  })
})
