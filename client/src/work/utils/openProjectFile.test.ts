import { afterEach, describe, expect, it, vi } from 'vitest'
import { openProjectFile } from './openProjectFile'

const mock = vi.hoisted(() => ({ listProjectFiles: vi.fn() }))
vi.mock('../api/matchaWork', () => ({ listProjectFiles: mock.listProjectFiles }))
afterEach(() => vi.restoreAllMocks())

describe('opening a starred file', () => {
  it('fetches a fresh link instead of using the stored URL', async () => {
    const tab = { opener: window, location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    mock.listProjectFiles.mockResolvedValue([{ id: 'file-1', storage_url: 'https://files.test/fresh' }])

    expect(await openProjectFile('project-1', 'file-1')).toBe(true)
    expect(mock.listProjectFiles).toHaveBeenCalledWith('project-1')
    expect(tab.location.href).toBe('https://files.test/fresh')
    expect(tab.opener).toBeNull()
  })

  it('closes the blank tab when access is lost', async () => {
    const tab = { opener: window, location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    mock.listProjectFiles.mockResolvedValue([])

    expect(await openProjectFile('project-1', 'file-1')).toBe(false)
    expect(tab.close).toHaveBeenCalled()
  })
})
