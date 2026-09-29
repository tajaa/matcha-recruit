import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AgentResultView from './AgentResultView'
import { agentErrorMessage } from '../../../api/matchaWork/agentCards'
import { ApiError } from '../../../../api/client'
import type { MWProjectTask } from '../../../types'

const mock = vi.hoisted(() => ({ list: vi.fn(), rerun: vi.fn() }))
vi.mock('../../../api/matchaWork', async () => ({
  ...(await vi.importActual<typeof import('../../../api/matchaWork/agentCards')>('../../../api/matchaWork/agentCards')),
  listAgentRuns: mock.list,
  rerunAgent: mock.rerun,
}))

const task = (over: Partial<MWProjectTask> = {}) =>
  ({ id: 'task-1', category: 'agent', board_column: 'review', progress_note: null, ...over }) as MWProjectTask

const pick = (name: string) => ({
  name, brand: 'Brand', why: ['USDA organic'],
  price: { amount: 4.99, currency: 'USD', source_url: 'https://shop.example/p' },
  rating: { value: 4.6, scale: 5, count: 812, source_url: 'https://shop.example/p' },
  reviews: [{ quote: 'Best balm', source_name: 'Reviews', url: 'https://reviews.example/r', sentiment: 'pos' }],
  images: [{ url: 'https://cdn.example/a.webp', page_url: 'https://shop.example/p', alt: name }],
  buy_links: [{ retailer: 'Shop', url: 'https://shop.example/buy', price: 4.99 }],
})

const result = (headline: string, changes: string | null = null) => ({
  schema: 'agent_result.v1', headline, summary: 'Summary text', answer_type: 'recommendation',
  criteria: [], top_pick: pick('Organic Balm'), alternatives: [pick('Alt Balm')], sections: [],
  caveats: [], sources: [{ title: 'Roundup', url: 'https://reviews.example/r' }], confidence: 'high',
  changes_from_previous: changes,
})

const run = (id: string, round: number, status: string, res: unknown = null) => ({
  id, round, status, result: res, error: null, search_calls: 2, model_calls: 3,
  created_at: null, started_at: null, completed_at: null, steps: [],
})

beforeEach(() => vi.clearAllMocks())

describe('AgentResultView', () => {
  it('renders the newest round with external links hardened and a round switcher', async () => {
    mock.list.mockResolvedValue({ runs: [
      run('r2', 2, 'done', result('Vegan pick', 'Only vegan options now.')),
      run('r1', 1, 'done', result('First pick')),
    ] })
    render(<AgentResultView projectId="p" task={task()} canEdit />)
    await screen.findByText('Vegan pick')
    expect(screen.getByText('Only vegan options now.')).toBeTruthy()
    const buy = screen.getAllByRole('link', { name: /Shop/ })[0]
    expect(buy.getAttribute('href')).toBe('https://shop.example/buy')
    expect(buy.getAttribute('rel')).toBe('noopener noreferrer nofollow')
    expect(buy.getAttribute('target')).toBe('_blank')
    fireEvent.click(screen.getByText('Round 1'))
    expect(await screen.findByText('First pick')).toBeTruthy()
  })

  it('shows live progress while a run works and offers no rerun', async () => {
    mock.list.mockResolvedValue({ runs: [run('r1', 1, 'running')] })
    render(<AgentResultView projectId="p" task={task({ board_column: 'in_progress', progress_note: 'Reading shop.example…' })} canEdit />)
    await screen.findByText('Reading shop.example…')
    expect(screen.queryByText('Run again')).toBeNull()
  })

  it('reruns a failed card and surfaces the monthly cap', async () => {
    mock.list.mockResolvedValue({ runs: [run('r1', 1, 'failed')] })
    mock.rerun.mockRejectedValue(new ApiError('429', 429, {
      detail: { code: 'agent_run_limit', limit: 40, used: 40, resets_at: '2026-10-01T00:00:00+00:00' },
    }))
    render(<AgentResultView projectId="p" task={task({ board_column: 'in_progress', progress_note: 'Agent stopped: x' })} canEdit />)
    fireEvent.click(await screen.findByText('Run again'))
    await waitFor(() => expect(screen.getByText(/used all 40 agent runs/)).toBeTruthy())
    expect(mock.rerun).toHaveBeenCalledWith('p', 'task-1')
  })

  it('hides rerun from read-only viewers', async () => {
    mock.list.mockResolvedValue({ runs: [run('r1', 1, 'failed')] })
    render(<AgentResultView projectId="p" task={task({ board_column: 'todo' })} canEdit={false} />)
    await screen.findByText(/stopped before finishing/)
    expect(screen.queryByText('Run again')).toBeNull()
  })
})

describe('AgentResultView after a redirect the queue refused', () => {
  it('offers Run again in Changes requested when nothing is working on the saved note', async () => {
    mock.list.mockResolvedValue({ runs: [run('r1', 1, 'done', result('First pick'))] })
    mock.rerun.mockResolvedValue({ run_id: 'r2', round: 2, status: 'queued' })
    render(<AgentResultView projectId="p" task={task({ board_column: 'changes_requested' })} canEdit />)
    await screen.findByText(/Your note is saved, but the agent isn't working on it yet/)
    fireEvent.click(screen.getByText('Run again'))
    await waitFor(() => expect(mock.rerun).toHaveBeenCalledWith('p', 'task-1'))
  })

  it('shows no hint or button while the redirect run is live', async () => {
    mock.list.mockResolvedValue({ runs: [run('r2', 2, 'running'), run('r1', 1, 'done', result('First pick'))] })
    render(<AgentResultView projectId="p" task={task({ board_column: 'changes_requested', progress_note: 'Working on your feedback…' })} canEdit />)
    await screen.findByText('Working on your feedback…')
    expect(screen.queryByText('Run again')).toBeNull()
    expect(screen.queryByText(/Your note is saved/)).toBeNull()
  })
})

describe('AgentResultView section Markdown', () => {
  it('renders no images and only http(s) links, hardened', async () => {
    const res = {
      ...result('Answer'),
      top_pick: null,
      alternatives: [],
      sections: [{ heading: 'How', body_md: 'Read [ok](https://ok.example/a) or [bad](javascript:alert(1)) ![pixel](https://evil.example/p.png)' }],
    }
    mock.list.mockResolvedValue({ runs: [run('r1', 1, 'done', res)] })
    const { container } = render(<AgentResultView projectId="p" task={task()} canEdit />)
    await screen.findByText('How')
    const ok = screen.getByText('ok').closest('a')
    expect(ok?.getAttribute('href')).toBe('https://ok.example/a')
    expect(ok?.getAttribute('rel')).toBe('noopener noreferrer nofollow')
    expect(screen.getByText(/bad/).closest('a')).toBeNull()
    expect(container.querySelector('img[src*="evil.example"]')).toBeNull()
  })
})

describe('agentErrorMessage', () => {
  it('maps plan and plain details', () => {
    expect(agentErrorMessage(new ApiError('x', 403, { detail: { code: 'plan_required' } }))).toMatch(/Pro plan/)
    expect(agentErrorMessage(new ApiError('x', 409, { detail: 'Already working' }))).toBe('Already working')
    expect(agentErrorMessage(new Error('boom'))).toBe('boom')
  })
})
