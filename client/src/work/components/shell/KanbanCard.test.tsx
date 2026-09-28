import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { MWProjectTask } from '../../types'
import KanbanCard from './KanbanCard'

const base = {
  id: 't1',
  title: 'Clear stale review state',
  board_column: 'in_progress',
  status: 'pending',
  priority: 'medium',
  category: 'bug',
  created_at: new Date().toISOString(),
  last_moved_at: null,
  assigned_name: 'Haley Haley',
  created_by_name: 'Haley Haley',
  subtask_total: 5,
  subtask_done: 3,
  attachments: [
    { id: 'a1', filename: 'shot.png', content_type: 'image/png', storage_url: 'https://cdn.example.com/a1.png' },
    { id: 'a2', filename: 'log.txt', content_type: 'text/plain', storage_url: 'https://cdn.example.com/a2.txt' },
  ],
} as unknown as MWProjectTask

function renderCard(patch: Partial<MWProjectTask> = {}, props: { ringed?: boolean; onMenu?: () => void; onClick?: () => void } = {}) {
  return render(
    <KanbanCard
      task={{ ...base, ...patch }}
      onClick={props.onClick ?? vi.fn()}
      onDragStart={vi.fn()}
      onDragEnd={vi.fn()}
      ringed={props.ringed}
      onMenu={props.onMenu}
    />,
  )
}

describe('KanbanCard', () => {
  it('keeps the face to the title and one quiet meta row', () => {
    const { container } = renderCard()
    expect(screen.getByText('Clear stale review state')).toBeTruthy()
    expect(screen.getByText('Bug')).toBeTruthy()
    expect(screen.getByText('3/5')).toBeTruthy()
    expect(screen.getByTitle('2 attachments').textContent).toBe('2')
    // The lane already names the column, and screenshots stay in the viewer.
    expect(screen.queryByText('In Progress')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
  })

  it('shows AutoPR state as a one-line strip, not a banner box', () => {
    renderCard({ progress_note: '🤖 AUTO SETUP · PR ready for review', pr_number: 543, pr_url: 'https://github.com/o/r/pull/543' })
    expect(screen.getByText('Auto setup')).toBeTruthy()
    expect(screen.getByText(/PR #543 is ready for review/)).toBeTruthy()
    const pr = screen.getByTitle('PR #543')
    expect(pr.getAttribute('href')).toBe('https://github.com/o/r/pull/543')
  })

  it('renders a stored non-http PR url as inert text', () => {
    renderCard({ pr_number: 7, pr_url: 'javascript:alert(1)' })
    expect(screen.getByTitle('PR #7').tagName).toBe('SPAN')
  })

  it('marks unseen changes with a dot and opens the menu without opening the card', () => {
    const onMenu = vi.fn()
    const onClick = vi.fn()
    renderCard({}, { ringed: true, onMenu, onClick })
    expect(screen.getByLabelText('Updated since you last looked')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Task actions'))
    expect(onMenu).toHaveBeenCalledTimes(1)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows why a card bounced while it sits in changes requested', () => {
    renderCard({ board_column: 'changes_requested', review_note: 'Tests missing', review_cycle_count: 2 })
    expect(screen.getByText('Tests missing')).toBeTruthy()
    expect(screen.getByTitle('Sent back from review 2 times').textContent).toBe('×2')
  })
})
