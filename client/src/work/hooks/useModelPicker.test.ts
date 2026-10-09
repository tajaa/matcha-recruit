import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { modelOptionsFor } from '../components/panels/constants'
import { useModelPicker } from './useModelPicker'

const mock = vi.hoisted(() => ({ claudeModels: false, pro: false, agentModel: null as string | null }))

vi.mock('./useEntitlements', () => ({
  useEntitlements: () => ({
    claudeModels: mock.claudeModels,
    agentModel: mock.agentModel,
    can: (feature: string) => feature === 'ai_model_pro' && mock.pro,
  }),
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

beforeEach(() => {
  mock.claudeModels = false
  mock.pro = false
  mock.agentModel = null
  vi.stubGlobal('localStorage', memoryStorage())
})
afterEach(() => vi.unstubAllGlobals())

describe('modelOptionsFor', () => {
  it('offers Claude only when the server has it, and Sonnet only with the pro model', () => {
    expect(ids(modelOptionsFor({ claude: false, pro: true }))).toEqual(['gemini-3.5-flash-lite', 'gemini-3.7-flash'])
    expect(ids(modelOptionsFor({ claude: true, pro: false }))).toEqual(
      ['gemini-3.5-flash-lite', 'gemini-3.7-flash', 'claude-haiku-5-5'],
    )
    expect(ids(modelOptionsFor({ claude: true, pro: true }))).toEqual(
      ['gemini-3.5-flash-lite', 'gemini-3.7-flash', 'claude-haiku-5-5', 'claude-sonnet-5-5'],
    )
  })
})

describe('modelOptionsFor with an admin agent model', () => {
  it('offers only Claude, always including the admin model', () => {
    expect(ids(modelOptionsFor({ claude: true, pro: false, agentModel: 'claude-haiku-5-5' }))).toEqual(['claude-haiku-5-5'])
    expect(ids(modelOptionsFor({ claude: true, pro: false, agentModel: 'claude-sonnet-5-5' }))).toEqual(
      ['claude-haiku-5-5', 'claude-sonnet-5-5'],
    )
  })
})

describe('useModelPicker', () => {
  it('defaults to the admin agent model over a stored Gemini pick', () => {
    localStorage.setItem('mw-model', 'gemini-3.7-flash')
    mock.claudeModels = true
    mock.agentModel = 'claude-sonnet-5-5'
    const { result } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('claude-sonnet-5-5')
    act(() => result.current.setSelectedModel('claude-haiku-5-5'))
    expect(result.current.selectedModel).toBe('claude-haiku-5-5')
  })


  it('defaults to Flash, then remembers a pick', () => {
    mock.claudeModels = true
    const { result } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('gemini-3.7-flash')
    act(() => result.current.setSelectedModel('claude-haiku-5-5'))
    expect(result.current.selectedModel).toBe('claude-haiku-5-5')
    expect(localStorage.getItem('mw-model')).toBe('claude-haiku-5-5')
  })

  it('reads a remembered pick that is no longer offered as the default', () => {
    localStorage.setItem('mw-model', 'claude-sonnet-5-5')
    mock.claudeModels = true
    const { result, rerender } = renderHook(() => useModelPicker())
    expect(result.current.selectedModel).toBe('gemini-3.7-flash') // no pro model
    mock.pro = true
    rerender()
    expect(result.current.selectedModel).toBe('claude-sonnet-5-5')
    mock.claudeModels = false
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
