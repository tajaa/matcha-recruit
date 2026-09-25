import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useJournals, sharedWithMe, journalDirtyPatch } from './useJournals'
import type { Journal } from '../../api/matchaWork/journals'

const mock = vi.hoisted(() => ({
  canPremium: false,
  listJournals: vi.fn(), listFolders: vi.fn(), createJournal: vi.fn(), updateJournal: vi.fn(),
  showPaywall: vi.fn(),
}))

vi.mock('../../hooks/useEntitlements', () => ({
  useEntitlements: () => ({ plan: 'free', can: () => mock.canPremium }),
}))
vi.mock('../../utils/paywall', () => ({ showPaywall: mock.showPaywall }))
vi.mock('../../api/matchaWork/journals', () => ({
  JOURNALS_CHANGED_EVENT: 'mw-journals-changed',
  listJournals: mock.listJournals,
  listJournalFolders: mock.listFolders,
  createJournal: mock.createJournal,
  updateJournal: mock.updateJournal,
}))

const journal = (overrides: Partial<Journal> = {}): Journal => ({
  id: 'one', title: 'First', description: null, color: null, icon: null,
  status: 'active', kind: 'note', folder_id: 'folder-a', created_by: 'owner', owner_name: 'Owner',
  created_at: '', updated_at: '', entry_count: 1, collaborator_count: 0,
  collaborator_role: null, preview: null, ...overrides,
})

beforeEach(() => {
  vi.clearAllMocks()
  mock.canPremium = false
  mock.listJournals.mockResolvedValue([journal()])
  mock.listFolders.mockResolvedValue([])
  mock.updateJournal.mockImplementation(async (_id: string, patch: object) => ({ ...journal(), ...patch }))
})

describe('journal mutations', () => {
  it('renames with only the dirty title field, retaining folder placement', async () => {
    const { result } = renderHook(() => useJournals())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.patch('one', journalDirtyPatch('title', 'Renamed')) })
    expect(mock.updateJournal).toHaveBeenCalledWith('one', { title: 'Renamed' })
    expect(result.current.journals[0].folder_id).toBe('folder-a')
  })

  it('moves to the hub root with an explicit null folder_id', async () => {
    const { result } = renderHook(() => useJournals())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.patch('one', journalDirtyPatch('folder_id', null)) })
    expect(mock.updateJournal).toHaveBeenCalledWith('one', { folder_id: null })
  })

  it('opens a paywall before premium creation on Free and sends no POST', async () => {
    const { result } = renderHook(() => useJournals())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { expect(await result.current.create('screenplay')).toBeNull() })
    expect(mock.showPaywall).toHaveBeenCalledWith('journals_full', 'lite', 'free')
    expect(mock.createJournal).not.toHaveBeenCalled()
  })

  it('lets Free users edit an existing premium journal', async () => {
    mock.listJournals.mockResolvedValue([journal({ kind: 'novel' })])
    const { result } = renderHook(() => useJournals())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.patch('one', { title: 'Next chapter' }) })
    expect(mock.updateJournal).toHaveBeenCalledWith('one', { title: 'Next chapter' })
    expect(mock.showPaywall).not.toHaveBeenCalled()
  })

  it('filters shared notes by collaborator role, regardless of owner name', () => {
    expect(sharedWithMe([
      journal({ id: 'owned', owner_name: 'Me' }),
      journal({ id: 'shared', collaborator_role: 'collaborator', owner_name: 'Other' }),
    ]).map((item) => item.id)).toEqual(['shared'])
  })
})
