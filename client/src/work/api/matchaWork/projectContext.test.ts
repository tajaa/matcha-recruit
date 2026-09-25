import { describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import { patchProjectElement, putGithubConnection } from './projectContext'

vi.mock('../../../api/client', () => ({ api: { patch: vi.fn(), put: vi.fn() } }))

describe('project context API', () => {
  it('preserves an opaque non-UUID element id', () => {
    patchProjectElement('project-1', 'repo:src/ui', { name: 'UI' })
    expect(api.patch).toHaveBeenCalledWith('/matcha-work/projects/project-1/elements/repo%3Asrc%2Fui', { name: 'UI' })
  })

  it('disconnects with an empty repo string', () => {
    putGithubConnection('project-1', '')
    expect(api.put).toHaveBeenCalledWith('/matcha-work/projects/project-1/github/connection', { repo: '', branch: null })
  })
})
