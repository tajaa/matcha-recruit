import { describe, expect, it, vi } from 'vitest'
import { autoSyncFromGithubIfStale } from './githubAutoSync'

const mock = vi.hoisted(() => ({ sync: vi.fn(), scan: vi.fn() }))
vi.mock('../api/matchaWork', () => ({ syncGithubProject: mock.sync, scanGithubCommits: mock.scan }))

describe('GitHub auto sync cooldown', () => {
  it('stamps before awaiting so concurrent tab opens sync once', async () => {
    let finish!: (result: { total_stored: number }) => void
    mock.sync.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const first = autoSyncFromGithubIfStale('sync-test-unique', true)
    const second = autoSyncFromGithubIfStale('sync-test-unique', true)
    expect(mock.sync).toHaveBeenCalledTimes(1)
    finish({ total_stored: 1 })
    expect(await first).toEqual({ total_stored: 1 })
    expect(await second).toBeNull()
    expect(await autoSyncFromGithubIfStale('sync-test-unique', true)).toBeNull()
  })
})
