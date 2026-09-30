import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PickUp, UpNext } from './HomeInsights'
import { groupTasks, pickUpItems } from './homeData'
import type { MWActivityItem, MWOpenTask } from '../api/matchaWork/dashboard'
import type { MWThread } from '../types'
import { chatLabel } from '../utils/chatLabel'

const task = (id: string, title: string, project = 'p1', extra: Partial<MWOpenTask> = {}): MWOpenTask => ({
  id, project_id: project, title, priority: 'high', status: 'open', due_date: null, progress_note: null,
  assigned_to: 'me', created_by: 'other', updated_at: '', project_title: project === 'p1' ? 'COLLAB' : 'WerkWerk',
  project_type: 'general', is_subtask: false, ...extra,
})

describe('Home: up next', () => {
  it('groups by workspace in the order the server ranked them, keeping task order', () => {
    const groups = groupTasks([task('a', 'A'), task('b', 'B', 'p2'), task('c', 'C'), task('d', 'D', 'p2')])
    expect(groups.map((g) => g.title)).toEqual(['COLLAB', 'WerkWerk'])
    expect(groups[0].tasks.map((t) => t.id)).toEqual(['a', 'c'])
  })

  it('names each workspace once, caps a long run, and marks late and subtask items', () => {
    const tasks = [
      task('1', 'First'), task('2', 'Second', 'p1', { due_date: '2000-01-02' }),
      task('3', 'Checklist item', 'p1', { is_subtask: true, parent_title: 'Parent task' }),
      task('4', 'Four'), task('5', 'Five'), task('6', 'Six'),
    ]
    render(<MemoryRouter><UpNext tasks={tasks} base="/espresso" perGroup={4} /></MemoryRouter>)
    expect(screen.getAllByText('COLLAB')).toHaveLength(1)
    expect(screen.getByText('Four')).toBeTruthy()
    expect(screen.queryByText('Five')).toBeNull()
    expect(screen.getByText('2 more in COLLAB')).toBeTruthy()
    expect(screen.getByText(/Late · Jan 2/)).toBeTruthy()
    expect(screen.getByText('Subtask of Parent task')).toBeTruthy()
  })

  it('says what shows up here when nothing is assigned', () => {
    render(<MemoryRouter><UpNext tasks={[]} base="/espresso" /></MemoryRouter>)
    expect(screen.getByText(/Nothing assigned to you/)).toBeTruthy()
  })
})

describe('Home: pick up where you left off', () => {
  const thread = (id: string, title: string, updated: string, status = 'active') =>
    ({ id, title, status, created_at: updated, updated_at: updated } as unknown as MWThread)
  const activity: MWActivityItem[] = [
    { kind: 'project', ref_id: 'p1', project_id: 'p1', title: 'COLLAB', project_type: 'general', updated_at: '2026-09-30T10:00:00Z' },
    { kind: 'thread', ref_id: 't1', project_id: null, title: 'Standing desk', project_type: null, updated_at: '2026-09-29T10:00:00Z' },
  ]

  it('merges recent chats into activity, newest first, without repeats or archived chats', () => {
    const items = pickUpItems(activity, [
      thread('t1', 'Standing desk', '2026-09-29T10:00:00Z'),
      thread('t2', 'New Chat Jun 4, 2026, 9:16 PM', '2026-09-30T12:00:00Z'),
      thread('t3', 'Old', '2026-09-30T13:00:00Z', 'archived'),
    ], '/espresso')
    expect(items.map((i) => i.key)).toEqual(['chat:t2', 'workspace:p1', 'chat:t1'])
    expect(items[0].title).toBe('Untitled chat')
    expect(items[1].path).toBe('/espresso/projects/p1')
    expect(items[2].path).toBe('/espresso/t1')
  })

  it('is never a dead end when empty', () => {
    render(<MemoryRouter><PickUp items={[]} /></MemoryRouter>)
    expect(screen.getByText(/Start a chat or open a workspace/)).toBeTruthy()
  })
})

describe('chatLabel', () => {
  it('hides the server date in an unnamed chat title and leaves real titles alone', () => {
    expect(chatLabel('New Chat Jun 4, 2026, 9:16 PM')).toBe('Untitled chat')
    expect(chatLabel('New Chat')).toBe('Untitled chat')
    expect(chatLabel('New Chat about socks')).toBe('New Chat about socks')
    expect(chatLabel('Standing desk')).toBe('Standing desk')
  })
})
