import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import CollabOverviewTab from './CollabOverviewTab'

const mock = vi.hoisted(() => ({ bundle: vi.fn(), connection: vi.fn(), suggestions: vi.fn() }))
vi.mock('../../api/matchaWork', () => ({ getProjectBundle: mock.bundle, getGithubConnection: mock.connection, listCommitSuggestions: mock.suggestions }))

describe('collab Overview', () => {
  it('counts distinct checklist items and links to suggestion review', async () => {
    mock.bundle.mockResolvedValue({ project: { title: 'Project' }, tasks: [], elements: [], done_total: 0 })
    mock.connection.mockResolvedValue({ connected: true, repo: 'org/repo' })
    mock.suggestions.mockResolvedValue([
      { id: 'one', subtask_id: 'sub-1', commit_short_sha: 'abc', commit_message: 'Fix A' },
      { id: 'two', subtask_id: 'sub-1', commit_short_sha: 'def', commit_message: 'Fix B' },
    ])
    const openElements = vi.fn()
    render(<CollabOverviewTab projectId="project-1" onOpenElements={openElements} onOpenBoard={vi.fn()} />)
    expect(await screen.findByText('Commit suggestions · 1 checklist item')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Review suggestions →'))
    expect(openElements).toHaveBeenCalledOnce()
  })
})
