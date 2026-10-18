import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RecapPlayer from './RecapPlayer'
import type { RecapDetail } from '../../types'

const mock = vi.hoisted(() => ({ playback: vi.fn() }))
vi.mock('../../api/matchaWork/recaps', () => ({ getRecapPlayback: mock.playback }))
const recap = { id: 'recap', title: 'Private recap', state: 'ready', chapters: [] } as unknown as RecapDetail
const signed = (n: number) => ({ video_url: `https://media.example.com/video-${n}.mp4`, poster_url: 'https://media.example.com/poster.png', expires_in: 300 })
const player = () => screen.getByLabelText('Private recap') as HTMLVideoElement

beforeEach(() => { vi.clearAllMocks(); Object.defineProperty(document, 'hidden', { configurable: true, value: false }) })
afterEach(() => { vi.useRealTimers() })
describe('recap playback', () => {
  it('keeps the loaded video while signed URLs refresh', async () => {
    vi.useFakeTimers()
    mock.playback.mockResolvedValueOnce(signed(1)).mockResolvedValueOnce(signed(2)).mockResolvedValue(signed(3))
    render(<RecapPlayer recap={recap} />)
    await act(async () => { await Promise.resolve() })
    expect(player().getAttribute('src')).toContain('video-1')
    await act(async () => { await vi.advanceTimersByTimeAsync(255_000) })
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await act(async () => { await Promise.resolve() })
    expect(mock.playback).toHaveBeenCalledTimes(3)
    expect(player().getAttribute('src')).toContain('video-1')
  })
  it('recovers from a media error where it left off and keeps playing', async () => {
    mock.playback.mockResolvedValueOnce(signed(1)).mockResolvedValue(signed(2))
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    render(<RecapPlayer recap={recap} />)
    await waitFor(() => expect(player().getAttribute('src')).toContain('video-1'))
    fireEvent.play(player())
    player().currentTime = 42
    fireEvent.error(player())
    await waitFor(() => expect(player().getAttribute('src')).toContain('video-2'))
    fireEvent.loadedMetadata(player())
    expect(player().currentTime).toBe(42)
    expect(play).toHaveBeenCalled()
    play.mockRestore()
  })
})
