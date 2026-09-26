import { describe, expect, it } from 'vitest'
import type { ReplayEvent, WeeklyReplay } from '../api/matchaWork/replay'
import { foldReplay, pacificWeekStart, replayRoundIndex } from './replay'

const event = (overrides: Partial<ReplayEvent>): ReplayEvent => ({
  id: 'event', task_id: 'task', event_type: 'column_change',
  from_column: 'todo', to_column: 'in_progress', actor_id: null,
  actor_name: null, actor_avatar_url: null, title: 'Ticket',
  created_at: '2026-09-22T18:00:00Z', ...overrides,
})

function replay(events: ReplayEvent[]): WeeklyReplay {
  return {
    week_start: '2026-09-21T07:00:00Z', week_end: '2026-09-28T07:00:00Z',
    starting_state: [
      { task_id: 'task', title: 'Ticket', column: 'todo', assignee_name: null, assignee_avatar_url: null },
      { task_id: 'old-done', title: 'Last week', column: 'done', assignee_name: null, assignee_avatar_url: null },
      { task_id: null, title: 'Unaddressable', column: 'todo', assignee_name: null, assignee_avatar_url: null },
    ], events,
  }
}

describe('Pacific replay week', () => {
  it('uses Pacific Monday even for an instant that is Tuesday in Tokyo', () => {
    expect(pacificWeekStart(new Date('2026-09-22T01:00:00Z'))).toBe('2026-09-21T07:00:00.000Z')
  })

  it('accounts for the Pacific DST offset across adjacent weeks', () => {
    expect(pacificWeekStart(new Date('2026-03-04T12:00:00Z'))).toBe('2026-03-02T08:00:00.000Z')
    expect(pacificWeekStart(new Date('2026-03-04T12:00:00Z'), 1)).toBe('2026-03-09T07:00:00.000Z')
  })
})

describe('replay fold', () => {
  it('ignores non-column events and never materializes a deleted unknown task', () => {
    const state = foldReplay(replay([
      event({ task_id: 'ghost', event_type: 'comment_added', to_column: 'review' }),
      event({ task_id: 'ghost', event_type: 'deleted', to_column: null }),
      event({ task_id: null, event_type: 'created' }),
    ]), 3)
    expect(state.map((task) => task.task_id)).toEqual(['task'])
    expect(state[0].column).toBe('todo')
  })

  it('excludes old Done cards until a move reopens them', () => {
    const data = replay([event({ task_id: 'old-done', from_column: 'done', to_column: 'review', title: 'Last week' })])
    expect(foldReplay(data, 0).map((task) => task.task_id)).toEqual(['task'])
    expect(foldReplay(data, 1).find((task) => task.task_id === 'old-done')?.column).toBe('review')
  })

  it('derives the round from kickoff events at or before the frame time', () => {
    const events = [event({ event_type: 'round_started', created_at: '2026-09-22T18:00:00Z' }),
      event({ event_type: 'round_started', created_at: '2026-09-22T18:01:00Z' })]
    expect(replayRoundIndex(events, 'task', '2026-09-22T18:00:00Z')).toBe(2)
    expect(replayRoundIndex(events, 'task', '2026-09-22T18:01:00Z')).toBe(3)
  })
})
