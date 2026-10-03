import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CommercialPlayer, SchedulingCommercial } from './SchedulingCommercial'
import { EMPTY_COMMERCIAL } from '../../types/landingMedia'
import { landingMedia } from '../../api/admin/landingMedia'

vi.mock('../../api/admin/landingMedia', () => ({ landingMedia: { getPublic: vi.fn() } }))
const settings = { ...EMPTY_COMMERCIAL, enabled: true, desktop_video_url: 'https://media.example.com/desktop.mp4', mobile_video_url: 'https://media.example.com/mobile.mp4', mobile_poster_url: 'https://media.example.com/mobile.webp' }
let mobile = false
beforeEach(() => {
  mobile = false
  vi.clearAllMocks()
  window.matchMedia = vi.fn((query) => ({ matches: mobile && query.includes('767px'), addEventListener: vi.fn(), removeEventListener: vi.fn() })) as unknown as typeof window.matchMedia
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
})

describe('scheduling commercial', () => {
  it('fetches only for the buyer variant and keeps the fallback on failure', async () => {
    vi.mocked(landingMedia.getPublic).mockRejectedValue(new Error('offline'))
    const view = render(<SchedulingCommercial enabled={false} fallback={<p>Schedule demo</p>} />)
    expect(landingMedia.getPublic).not.toHaveBeenCalled()
    view.rerender(<SchedulingCommercial enabled fallback={<p>Schedule demo</p>} />)
    await waitFor(() => expect(landingMedia.getPublic).toHaveBeenCalledOnce())
    expect(screen.getByText('Schedule demo')).toBeTruthy()
  })
  it('uses mobile edit and poster on phones, with desktop fallback', () => {
    mobile = true
    const view = render(<CommercialPlayer settings={settings} fallback={<p>Schedule demo</p>} />)
    let video = screen.getByLabelText('Matcha scheduling commercial')
    expect(video.getAttribute('src')).toBe(settings.mobile_video_url)
    expect(video.getAttribute('poster')).toBe(settings.mobile_poster_url)
    view.rerender(<CommercialPlayer settings={{ ...settings, mobile_video_url: null }} fallback={<p>Schedule demo</p>} />)
    video = screen.getByLabelText('Matcha scheduling commercial')
    expect(video.getAttribute('src')).toBe(settings.desktop_video_url)
    expect(video.getAttribute('poster')).toBeNull()
  })
  it('lets visitors watch with sound, seek, skip, and replay', () => {
    render(<CommercialPlayer settings={settings} fallback={<p>Schedule demo</p>} />)
    const video = screen.getByLabelText('Matcha scheduling commercial') as HTMLVideoElement
    expect(video.muted).toBe(true)
    fireEvent.click(screen.getAllByRole('button', { name: 'Watch with sound' })[0])
    expect(video.muted).toBe(false)
    expect(video.controls).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Skip to the schedule' }))
    expect(screen.getByText('Schedule demo')).toBeTruthy()
    expect(screen.queryByLabelText('Matcha scheduling commercial')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Watch the film' }))
    expect(screen.getByLabelText('Matcha scheduling commercial')).toBeTruthy()
  })
  it('falls back to the schedule when the video fails', () => {
    render(<CommercialPlayer settings={settings} fallback={<p>Schedule demo</p>} />)
    fireEvent.error(screen.getByLabelText('Matcha scheduling commercial'))
    expect(screen.getByText('Schedule demo')).toBeTruthy()
  })
})
