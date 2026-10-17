import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ItemPane from './ItemPane'
import type { AgentTaskItemDetail } from '../../types'

const item: AgentTaskItemDetail = { id: 'i1', title: 'The Avery', user_state: 'new' }

function pane(props: Partial<Parameters<typeof ItemPane>[0]> = {}) {
  const handlers = { onRetry: vi.fn(), onDismissError: vi.fn(), onClose: vi.fn() }
  render(
    <ItemPane
      item={null}
      loadError={null}
      error={null}
      columns={[]}
      canFollowUp={false}
      busy={false}
      onSetState={vi.fn()}
      onSaveNotes={vi.fn()}
      onMoreLikeThis={vi.fn()}
      onAskEspresso={vi.fn()}
      onAction={vi.fn()}
      {...handlers}
      {...props}
    />,
  )
  return handlers
}

describe('ItemPane', () => {
  it('spins while the finding loads', () => {
    pane()
    expect(screen.getByLabelText('Loading')).toBeTruthy()
  })

  it("says the finding couldn't load and tries again", () => {
    const { onRetry } = pane({ loadError: "Couldn't load this finding." })
    expect(screen.queryByLabelText('Loading')).toBeNull()
    expect(screen.getByText("Couldn't load this finding.")).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it("shows a change that didn't go through over the finding, and dismisses it", () => {
    const { onDismissError } = pane({ item, error: "Couldn't save that." })
    expect(screen.getByRole('alert').textContent).toContain("Couldn't save that.")
    expect(screen.getByText('The Avery')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss the message' }))
    expect(onDismissError).toHaveBeenCalledOnce()
  })
})
