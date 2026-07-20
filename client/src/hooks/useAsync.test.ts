import { describe, it, expect, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAsync, useAsyncAction } from './useAsync'

/** A promise whose settlement the test controls, so overlapping runs can be
 *  resolved out of order on purpose. */
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('useAsync', () => {
  it('starts loading and resolves data', async () => {
    const { result } = renderHook(() => useAsync(() => Promise.resolve('x'), []))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBe('x')
    expect(result.current.error).toBeNull()
  })

  it('captures the error message and leaves data undefined', async () => {
    const { result } = renderHook(() => useAsync(() => Promise.reject(new Error('boom')), []))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe('boom')
    expect(result.current.data).toBeUndefined()
  })

  it('re-runs when deps change', async () => {
    const fn = vi.fn().mockResolvedValue('a')
    const { result, rerender } = renderHook(({ id }) => useAsync(fn, [id]), {
      initialProps: { id: 1 },
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fn).toHaveBeenCalledTimes(1)
    rerender({ id: 2 })
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2))
  })

  it('does NOT re-run when deps are unchanged', async () => {
    const fn = vi.fn().mockResolvedValue('a')
    const { result, rerender } = renderHook(({ id }) => useAsync(fn, [id]), {
      initialProps: { id: 1 },
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    rerender({ id: 1 })
    rerender({ id: 1 })
    expect(fn).toHaveBeenCalledTimes(1)
  })

  // The no-flash rule: a reload keeps the previous rows on screen so a filter
  // change re-renders in place instead of blanking the table.
  it('keeps previous data visible during a reload', async () => {
    const d1 = deferred<string>()
    const d2 = deferred<string>()
    let call = 0
    const { result } = renderHook(() => useAsync(() => (++call === 1 ? d1.promise : d2.promise), []))
    await act(async () => { d1.resolve('first') })
    expect(result.current.data).toBe('first')

    act(() => { result.current.reload() })
    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBe('first') // still there, not cleared

    await act(async () => { d2.resolve('second') })
    expect(result.current.data).toBe('second')
  })

  // Two overlapping runs where the FIRST settles last: without a run counter the
  // stale response wins by landing last, which is how a fast filter click ends
  // up showing the previous filter's rows.
  it('discards an out-of-order response from a superseded run', async () => {
    const slowFirst = deferred<string>()
    const fastSecond = deferred<string>()
    let call = 0
    const { result } = renderHook(() =>
      useAsync(() => (++call === 1 ? slowFirst.promise : fastSecond.promise), []),
    )

    act(() => { result.current.reload() }) // run 2 supersedes run 1
    await act(async () => { fastSecond.resolve('newest') })
    expect(result.current.data).toBe('newest')

    await act(async () => { slowFirst.resolve('stale') })
    expect(result.current.data).toBe('newest') // stale run did not overwrite
  })

  it('does not let a superseded run clear the loading flag', async () => {
    const slowFirst = deferred<string>()
    const pendingSecond = deferred<string>()
    let call = 0
    const { result } = renderHook(() =>
      useAsync(() => (++call === 1 ? slowFirst.promise : pendingSecond.promise), []),
    )
    act(() => { result.current.reload() })
    await act(async () => { slowFirst.resolve('stale') })
    // Run 2 is still in flight, so the hook must still read as loading.
    expect(result.current.loading).toBe(true)
  })

  it('clears a previous error once a later run succeeds', async () => {
    const d1 = deferred<string>()
    const d2 = deferred<string>()
    let call = 0
    const { result } = renderHook(() => useAsync(() => (++call === 1 ? d1.promise : d2.promise), []))
    await act(async () => { d1.reject(new Error('nope')) })
    expect(result.current.error).toBe('nope')

    act(() => { result.current.reload() })
    await act(async () => { d2.resolve('ok') })
    expect(result.current.error).toBeNull()
    expect(result.current.data).toBe('ok')
  })

  it('reads the latest fn without needing it memoised', async () => {
    let value = 'first'
    const { result, rerender } = renderHook(() => useAsync(() => Promise.resolve(value), []))
    await waitFor(() => expect(result.current.data).toBe('first'))
    value = 'second'
    rerender()
    act(() => { result.current.reload() })
    await waitFor(() => expect(result.current.data).toBe('second'))
  })

  it('supports a guarded fn that resolves null while waiting on an id', async () => {
    const { result, rerender } = renderHook(
      ({ id }) => useAsync(() => (id ? Promise.resolve(`got-${id}`) : Promise.resolve(null)), [id]),
      { initialProps: { id: '' } },
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBeNull()
    rerender({ id: 'abc' })
    await waitFor(() => expect(result.current.data).toBe('got-abc'))
  })

  it('setData applies an optimistic update without a fetch', async () => {
    const fn = vi.fn().mockResolvedValue(['a'])
    const { result } = renderHook(() => useAsync<string[]>(fn, []))
    await waitFor(() => expect(result.current.data).toEqual(['a']))
    act(() => { result.current.setData((prev) => [...(prev ?? []), 'b']) })
    expect(result.current.data).toEqual(['a', 'b'])
    expect(fn).toHaveBeenCalledTimes(1)
  })
})

describe('useAsyncAction', () => {
  it('resolves the result and toggles busy', async () => {
    const { result } = renderHook(() => useAsyncAction(async (n: number) => n * 2))
    expect(result.current.busy).toBe(false)
    let out: number | undefined
    await act(async () => { out = await result.current.run(21) })
    expect(out).toBe(42)
    expect(result.current.busy).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('resolves undefined and records the error instead of throwing', async () => {
    const { result } = renderHook(() =>
      useAsyncAction(async () => { throw new Error('save failed') }),
    )
    let out: unknown = 'sentinel'
    await act(async () => { out = await result.current.run() })
    expect(out).toBeUndefined()
    expect(result.current.error).toBe('save failed')
    expect(result.current.busy).toBe(false)
  })

  it('clears a previous error when a later run starts', async () => {
    let shouldFail = true
    const { result } = renderHook(() =>
      useAsyncAction(async () => {
        if (shouldFail) throw new Error('first failed')
        return 'ok'
      }),
    )
    await act(async () => { await result.current.run() })
    expect(result.current.error).toBe('first failed')
    shouldFail = false
    await act(async () => { await result.current.run() })
    expect(result.current.error).toBeNull()
  })

  it('reset clears busy and error', async () => {
    const { result } = renderHook(() =>
      useAsyncAction(async () => { throw new Error('x') }),
    )
    await act(async () => { await result.current.run() })
    expect(result.current.error).toBe('x')
    act(() => { result.current.reset() })
    expect(result.current.error).toBeNull()
    expect(result.current.busy).toBe(false)
  })
})
