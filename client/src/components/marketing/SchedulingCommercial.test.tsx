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
  it('gives viewers a Sound off / Sound on button once they watch with sound', () => {
    render(<CommercialPlayer settings={settings} fallback={<p>Schedule demo</p>} />)
    const video = screen.getByLabelText('Matcha scheduling commercial') as HTMLVideoElement
    expect(screen.queryByRole('button', { name: /^Sound o/ })).toBeNull()
    fireEvent.click(screen.getAllByRole('button', { name: 'Watch with sound' })[0])
    expect(video.muted).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Sound off' }))
    expect(video.muted).toBe(true)
    expect(screen.queryByRole('button', { name: 'Sound off' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Sound on' }))
    expect(video.muted).toBe(false)
    // Muting through the native player controls keeps the page button truthful.
    video.muted = true
    fireEvent.volumeChange(video)
    expect(screen.getByRole('button', { name: 'Sound on' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Skip to the schedule' }))
    expect(screen.getByText('Schedule demo')).toBeTruthy()
  })
  it('treats settings saved before the sound option existed as sound on', () => {
    const legacy: Partial<typeof settings> = { ...settings }
    delete legacy.sound_enabled
    render(<CommercialPlayer settings={legacy as typeof settings} fallback={<p>Schedule demo</p>} />)
    expect(screen.getAllByRole('button', { name: 'Watch with sound' }).length).toBeGreaterThan(0)
  })
  describe('silent mode (sound turned off in the admin)', () => {
    const silent = { ...settings, sound_enabled: false }
    it('never offers sound: always muted, no native controls, no sound buttons', () => {
      render(<CommercialPlayer settings={silent} fallback={<p>Schedule demo</p>} />)
      const video = screen.getByLabelText('Matcha scheduling commercial') as HTMLVideoElement
      expect(video.muted).toBe(true)
      expect(video.controls).toBe(false)
      expect(screen.queryByRole('button', { name: /sound/i })).toBeNull()
      fireEvent.play(video)
      fireEvent.ended(video)
      expect(video.muted).toBe(true)
      expect(video.controls).toBe(false)
      expect(screen.queryByRole('button', { name: /sound/i })).toBeNull()
    })
    it('plays, pauses, replays, and can still be skipped', () => {
      render(<CommercialPlayer settings={silent} fallback={<p>Schedule demo</p>} />)
      const video = screen.getByLabelText('Matcha scheduling commercial') as HTMLVideoElement
      fireEvent.click(screen.getAllByRole('button', { name: 'Play film' })[0])
      expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1)
      fireEvent.play(video)
      expect(screen.queryByRole('button', { name: 'Play film' })).toBeNull()
      fireEvent.click(screen.getByRole('button', { name: 'Pause film' }))
      expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
      fireEvent.pause(video)
      expect(screen.getAllByRole('button', { name: 'Play film' }).length).toBeGreaterThan(0)
      fireEvent.click(screen.getAllByRole('button', { name: 'Play film' })[0])
      fireEvent.play(video)
      fireEvent.ended(video)
      expect(screen.getAllByRole('button', { name: 'Watch again' }).length).toBeGreaterThan(0)
      fireEvent.click(screen.getAllByRole('button', { name: 'Watch again' })[0])
      expect(video.currentTime).toBe(0)
      fireEvent.click(screen.getByRole('button', { name: 'Skip to the schedule' }))
      expect(screen.getByText('Schedule demo')).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: 'Watch the film' }))
      expect((screen.getByLabelText('Matcha scheduling commercial') as HTMLVideoElement).muted).toBe(true)
    })
  })
  it('removes the browser download entry and the right-click save menu', () => {
    render(<CommercialPlayer settings={settings} fallback={<p>Schedule demo</p>} />)
    const video = screen.getByLabelText('Matcha scheduling commercial')
    expect(video.getAttribute('controlslist')).toBe('nodownload')
    expect(fireEvent.contextMenu(video)).toBe(false)
  })
  it('falls back to the schedule when the video fails', () => {
    render(<CommercialPlayer settings={settings} fallback={<p>Schedule demo</p>} />)
    fireEvent.error(screen.getByLabelText('Matcha scheduling commercial'))
    expect(screen.getByText('Schedule demo')).toBeTruthy()
  })
})
