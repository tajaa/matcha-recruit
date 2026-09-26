import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import JournalEditor from './JournalEditor'
import type { Journal } from '../../api/matchaWork/journals'

const mock = vi.hoisted(() => ({
  listEntries: vi.fn(), createEntry: vi.fn(), updateEntry: vi.fn(),
}))
vi.mock('../../api/matchaWork/journals', () => ({
  listJournalEntries: mock.listEntries,
  createJournalEntry: mock.createEntry,
  updateJournalEntry: mock.updateEntry,
}))
vi.mock('./CollaboratorsModal', () => ({ default: () => null }))

const journal: Journal = {
  id: 'journal-one', title: 'Note', description: null, color: null, icon: null,
  status: 'active', kind: 'note', folder_id: null, created_by: 'owner', owner_name: 'Owner',
  created_at: '', updated_at: '', entry_count: 1, collaborator_count: 0,
  collaborator_role: null, preview: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  mock.listEntries.mockResolvedValue([{
    id: 'entry-one', journal_id: 'journal-one', author_id: 'owner', title: null,
    content: 'Old text', entry_date: null, created_at: '', updated_at: '',
  }])
  mock.updateEntry.mockResolvedValue({})
})

describe('JournalEditor', () => {
  it('flushes only changed entry content on blur', async () => {
    const changed = vi.fn()
    render(<JournalEditor journal={journal} folders={[]} userId="owner" onRename={vi.fn()} onMove={vi.fn()} onChanged={changed} />)
    const editor = await screen.findByRole('textbox', { name: 'Journal content' })
    await waitFor(() => expect(editor).toHaveValue('Old text'))
    fireEvent.change(editor, { target: { value: 'New text' } })
    fireEvent.blur(editor)
    await waitFor(() => expect(mock.updateEntry).toHaveBeenCalledWith('journal-one', 'entry-one', { content: 'New text' }))
    expect(changed).toHaveBeenCalled()
  })

  it('keeps another author’s entry read only for a collaborator', async () => {
    render(<JournalEditor journal={journal} folders={[]} userId="collaborator" onRename={vi.fn()} onMove={vi.fn()} onChanged={vi.fn()} />)
    const editor = await screen.findByRole('textbox', { name: 'Journal content' })
    await waitFor(() => expect(editor).toHaveValue('Old text'))
    expect(editor).toHaveAttribute('readonly')
    expect(screen.getByRole('button', { name: 'Write my own entry' })).toBeInTheDocument()
  })

  it('coalesces edits inside the save delay into one PATCH', async () => {
    render(<JournalEditor journal={journal} folders={[]} userId="owner" onRename={vi.fn()} onMove={vi.fn()} onChanged={vi.fn()} />)
    const editor = await screen.findByRole('textbox', { name: 'Journal content' })
    await waitFor(() => expect(editor).toHaveValue('Old text'))
    fireEvent.change(editor, { target: { value: 'First draft' } })
    fireEvent.change(editor, { target: { value: 'Final draft' } })
    await waitFor(() => expect(mock.updateEntry).toHaveBeenCalledTimes(1), { timeout: 2_000 })
    expect(mock.updateEntry).toHaveBeenCalledWith('journal-one', 'entry-one', { content: 'Final draft' })
  })

  it('flushes a pending edit when leaving the journal', async () => {
    const view = render(<JournalEditor journal={journal} folders={[]} userId="owner" onRename={vi.fn()} onMove={vi.fn()} onChanged={vi.fn()} />)
    const editor = await screen.findByRole('textbox', { name: 'Journal content' })
    await waitFor(() => expect(editor).toHaveValue('Old text'))
    fireEvent.change(editor, { target: { value: 'Saved on leave' } })
    view.unmount()
    await waitFor(() => expect(mock.updateEntry).toHaveBeenCalledWith('journal-one', 'entry-one', { content: 'Saved on leave' }))
  })

  it('applies heading shortcuts by physical key so macOS Option layouts work', async () => {
    render(<JournalEditor journal={journal} folders={[]} userId="owner" onRename={vi.fn()} onMove={vi.fn()} onChanged={vi.fn()} />)
    const editor = await screen.findByRole('textbox', { name: 'Journal content' }) as HTMLTextAreaElement
    await waitFor(() => expect(editor).toHaveValue('Old text'))
    editor.setSelectionRange(3, 3)
    // macOS reports Option+Shift+1 as key "⁄"; only `code` identifies the key.
    fireEvent.keyDown(editor, { key: '⁄', code: 'Digit1', altKey: true, shiftKey: true })
    expect(editor).toHaveValue('# Old text')
    fireEvent.keyDown(editor, { key: 'ˇ', code: 'KeyT', altKey: true, shiftKey: true })
    expect(editor).toHaveValue('- [ ] Old text')
  })
})
