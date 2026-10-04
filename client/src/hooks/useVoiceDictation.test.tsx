import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useVoiceDictation } from './useVoiceDictation'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

describe('useVoiceDictation', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('cancels a pending microphone grant without affecting a newer start', async () => {
    const permission = deferred<MediaStream>()
    const nextPermission = deferred<MediaStream>()
    const getUserMedia = vi.fn().mockReturnValueOnce(permission.promise).mockReturnValueOnce(nextPermission.promise)
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
    const oldTrack = { stop: vi.fn() }
    const { result, unmount } = renderHook(() => useVoiceDictation())
    let first!: Promise<void>
    let second!: Promise<void>
    act(() => { first = result.current.start() })
    act(() => result.current.cancel())
    act(() => { second = result.current.start() })
    await act(async () => { permission.resolve({ getTracks: () => [oldTrack] } as unknown as MediaStream); await first })
    expect(oldTrack.stop).toHaveBeenCalledOnce()
    expect(result.current.status).toBe('idle')
    expect(getUserMedia).toHaveBeenCalledTimes(2)
    unmount()
    const nextTrack = { stop: vi.fn() }
    await act(async () => { nextPermission.resolve({ getTracks: () => [nextTrack] } as unknown as MediaStream); await second })
    expect(nextTrack.stop).toHaveBeenCalledOnce()
  })

  it('does not let an old flush or rejected microphone start stop a newer recording', async () => {
    vi.useFakeTimers()
    const track = { stop: vi.fn() }
    const newerTrack = { stop: vi.fn() }
    const rejected = deferred<MediaStream>()
    const getUserMedia = vi.fn()
      .mockReturnValueOnce(rejected.promise)
      .mockResolvedValueOnce({ getTracks: () => [track] })
      .mockResolvedValueOnce({ getTracks: () => [newerTrack] })
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
    vi.stubGlobal('AudioContext', class {
      audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) }
      destination = {}
      createMediaStreamSource() { return { connect: vi.fn() } }
      createGain() { return { gain: { value: 0 }, connect: vi.fn() } }
      close() { return Promise.resolve() }
    })
    vi.stubGlobal('AudioWorkletNode', class {
      port = { postMessage: vi.fn(), onmessage: null }
      connect = vi.fn()
      disconnect = vi.fn()
    })
    const { result } = renderHook(() => useVoiceDictation())
    let obsoleteStart!: Promise<void>
    act(() => { obsoleteStart = result.current.start() })
    act(() => result.current.cancel())
    await act(async () => { await result.current.start() })
    let obsoleteStop!: Promise<Blob | null>
    act(() => { obsoleteStop = result.current.stop() })
    act(() => result.current.cancel())
    await act(async () => { await result.current.start() })
    await act(async () => {
      rejected.reject(new Error('Old microphone denied'))
      await obsoleteStart
      vi.advanceTimersByTime(80)
      expect(await obsoleteStop).toBeNull()
    })
    expect(result.current.status).toBe('recording')
    expect(track.stop).toHaveBeenCalledOnce()
    expect(newerTrack.stop).not.toHaveBeenCalled()
  })

  it('drops queued PCM frames from a cancelled recording', async () => {
    vi.useFakeTimers()
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    })
    vi.stubGlobal('AudioContext', class {
      audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) }
      destination = {}
      createMediaStreamSource() { return { connect: vi.fn() } }
      createGain() { return { gain: { value: 0 }, connect: vi.fn() } }
      close() { return Promise.resolve() }
    })
    const nodes: { port: { onmessage: ((event: { data: ArrayBuffer }) => void) | null } }[] = []
    vi.stubGlobal('AudioWorkletNode', class {
      port = { postMessage: vi.fn(), onmessage: null }
      connect = vi.fn()
      disconnect = vi.fn()
      constructor() { nodes.push(this) }
    })
    const { result } = renderHook(() => useVoiceDictation())
    await act(async () => { await result.current.start() })
    act(() => result.current.cancel())
    await act(async () => { await result.current.start() })
    nodes[0].port.onmessage?.({ data: new Int16Array([11]).buffer })
    nodes[1].port.onmessage?.({ data: new Int16Array([22]).buffer })
    let stop!: Promise<Blob | null>
    act(() => { stop = result.current.stop() })
    await act(async () => {
      vi.advanceTimersByTime(80)
      expect((await stop)?.size).toBe(46)
    })
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
