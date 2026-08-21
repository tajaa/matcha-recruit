import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useVoiceDictation } from './useVoiceDictation'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('useVoiceDictation', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('deduplicates microphone starts while permission is pending', async () => {
    const permission = deferred<MediaStream>()
    const getUserMedia = vi.fn().mockReturnValue(permission.promise)
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    })
    const track = { stop: vi.fn() }
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    const { result, unmount } = renderHook(() => useVoiceDictation())

    let first!: Promise<void>
    let second!: Promise<void>
    act(() => {
      first = result.current.start()
      second = result.current.start()
    })

    expect(getUserMedia).toHaveBeenCalledOnce()
    unmount()
    await act(async () => {
      permission.resolve(stream)
      await Promise.all([first, second])
    })
    expect(track.stop).toHaveBeenCalledOnce()
  })

  it('stops a stream granted after the hook unmounts', async () => {
    const permission = deferred<MediaStream>()
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockReturnValue(permission.promise) },
    })
    const track = { stop: vi.fn() }
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    const { result, unmount } = renderHook(() => useVoiceDictation())

    let start!: Promise<void>
    act(() => { start = result.current.start() })
    unmount()
    await act(async () => {
      permission.resolve(stream)
      await start
    })

    expect(track.stop).toHaveBeenCalledOnce()
  })
})
