import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { modelOptionsFor, type ChatModelRow } from '../components/panels/constants'
import { useModelPicker } from './useModelPicker'

const mock = vi.hoisted(() => ({
  chatModels: null as { id: string; locked: boolean }[] | null,
  defaultChatModel: null as string | null,
}))

vi.mock('./useEntitlements', () => ({
  useEntitlements: () => ({ chatModels: mock.chatModels, defaultChatModel: mock.defaultChatModel }),
}))

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value) },
    removeItem: (key) => { values.delete(key) },
    clear: () => values.clear(),
    key: () => null,
    get length() { return values.size },
  }
}

const ids = (options: { id: string }[]) => options.map((option) => option.id)
const row = (id: string, locked = false): ChatModelRow => ({ id, locked })

// What the server sends (matcha_work_ai._models.picker_models).
const ALL_ROWS = [
  row('gemini-3.5-flash-lite'), row('gemini-3.7-flash'), row('claude-haiku-5-5'), row('claude-sonnet-5-5', true),
]
const ADMIN_ROWS = [row('claude-haiku-5-5'), row('claude-sonnet-5-5')]

beforeEach(() => {
  mock.chatModels = null
  mock.defaultChatModel = null
  vi.stubGlobal('localStorage', memoryStorage())
})
afterEach(() => vi.unstubAllGlobals())

describe('modelOptionsFor', () => {
  it('shows the Gemini rows until the server answers', () => {
    expect(ids(modelOptionsFor(null))).toEqual(['gemini-3.5-flash-lite', 'gemini-3.7-flash'])
  })

  it('shows the server rows in menu order and leaves locked ones out', () => {
    expect(ids(modelOptionsFor(ALL_ROWS))).toEqual(['gemini-3.5-flash-lite', 'gemini-3.7-flash', 'claude-haiku-5-5'])
    expect(ids(modelOptionsFor([...ADMIN_ROWS].reverse()))).toEqual(['claude-haiku-5-5', 'claude-sonnet-5-5'])
  })
})

describe('useModelPicker', () => {
  it('starts on the server default over a remembered pick it no longer offers', () => {
    localStorage.setItem('mw-model', 'gemini-3.7-flash')
    mock.chatModels = ADMIN_ROWS
    mock.defaultChatModel = 'claude-sonnet-5-5'
    const { result } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('claude-sonnet-5-5')
    act(() => result.current.setSelectedModel('claude-haiku-5-5'))
    expect(result.current.selectedModel).toBe('claude-haiku-5-5')
  })

  it('defaults to Flash, then remembers a pick', () => {
    mock.chatModels = ALL_ROWS
    const { result } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('gemini-3.7-flash')
    act(() => result.current.setSelectedModel('claude-haiku-5-5'))
    expect(result.current.selectedModel).toBe('claude-haiku-5-5')
    expect(localStorage.getItem('mw-model')).toBe('claude-haiku-5-5')
  })

  it('reads a remembered pick that is locked or gone as the default', () => {
    localStorage.setItem('mw-model', 'claude-sonnet-5-5')
    mock.chatModels = ALL_ROWS
    const { result, rerender } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('gemini-3.7-flash') // Sonnet locked on this plan
    mock.chatModels = ALL_ROWS.map((r) => ({ ...r, locked: false }))
    rerender()
    expect(result.current.selectedModel).toBe('claude-sonnet-5-5')
    mock.chatModels = null
    rerender()
    expect(result.current.selectedModel).toBe('gemini-3.7-flash')
  })

  it('maps the old Flash Lite id the pickers used to store', () => {
    localStorage.setItem('mw-model', 'gemini-3.7-flash-lite')
    const { result } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('gemini-3.5-flash-lite')
  })

  it('keeps working when storage is blocked', () => {
    const blocked = () => { throw new Error('blocked') }
    vi.stubGlobal('localStorage', { getItem: blocked, setItem: blocked })
    const { result } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('gemini-3.7-flash')
    act(() => result.current.setSelectedModel('gemini-3.5-flash-lite'))
    expect(result.current.selectedModel).toBe('gemini-3.5-flash-lite')
  })
})
