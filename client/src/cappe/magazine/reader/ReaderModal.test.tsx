import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReaderModal from './ReaderModal'
import type { ReaderAnnotationBody } from './annotationTypes'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api }))
const props = () => ({ html: '<article class="mz-story"><p>Hello world</p></article>', title: 'Coast',
  endpoint: '/reader/magazines/salt/stories/coast/annotations', canAnnotate: true, asText: false,
  prepare: vi.fn(), onLink: vi.fn(), onClose: vi.fn(), onTextView: vi.fn() })

beforeEach(() => {
  api.get.mockResolvedValue({ annotations: [] })
  api.put.mockImplementation((path: string, body: ReaderAnnotationBody) => Promise.resolve({ ...body, id: path.split('/').at(-1) }))
  api.delete.mockResolvedValue({ deleted: true })
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute('open') } })
})
function load() {
  const frame = screen.getByTitle('Coast') as HTMLIFrameElement
  const doc = frame.contentDocument!
  doc.body.innerHTML = '<article class="mz-story"><p>Hello world</p></article>'
  fireEvent.load(frame)
  return { frame, doc }
}
async function select(doc: Document) {
  const text = doc.querySelector('p')!.firstChild!
  const range = doc.createRange(); range.setStart(text, 0); range.setEnd(text, 5)
  doc.getSelection()!.removeAllRanges(); doc.getSelection()!.addRange(range)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Highlight' })).toBeEnabled())
}

describe('reader modal', () => {
  it('opens as a modal, keeps native iframe selection focused, and closes', async () => {
    const p = props(); render(<ReaderModal {...p} />)
    expect(screen.getByRole('dialog')).toHaveAttribute('open')
    const { frame } = load()
    const blur = vi.spyOn(frame, 'blur')
    await new Promise((r) => setTimeout(r, 300))
    expect(blur).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close reader' }))
    expect(p.onClose).toHaveBeenCalledOnce()
  })
  it('retains the selection and retry UUID after a save failure, paints, reloads and deletes', async () => {
    const p = props(); render(<ReaderModal {...p} />)
    const { doc } = load(); await select(doc)
    api.put.mockRejectedValueOnce(new Error('Offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your selection and comment are kept')
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (1)' })).toBeInTheDocument())
    expect(api.put.mock.calls[0][0]).toBe(api.put.mock.calls[1][0])
    expect(api.put.mock.calls[1][1].quote.exact).toBe('Hello')
    await waitFor(() => expect(doc.querySelector('[data-reader-note]')?.textContent).toBe('Hello'))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Notes (1)' }))
    api.delete.mockRejectedValueOnce(new Error('Delete failed'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete highlight' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Delete failed')
    expect(screen.getByRole('button', { name: 'Notes (1)' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete highlight' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (0)' })).toBeInTheDocument())
    await waitFor(() => expect(doc.querySelector('[data-reader-note]')).toBeNull())
  })
  it('saves a page comment without a selection and guards unsaved comment navigation', async () => {
    const p = props(); render(<ReaderModal {...p} />); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Remember 🌍' } })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(screen.getByRole('button', { name: 'Close reader' }))
    expect(confirm).toHaveBeenCalledOnce(); expect(p.onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1]).toMatchObject({ kind: 'comment', page: 1, quote: null, text: 'Remember 🌍' })
    expect(await screen.findByText('Remember 🌍')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close reader' }))
    expect(p.onClose).toHaveBeenCalledOnce()
  })
  it('keeps reading available when note loading fails, and retries loading', async () => {
    api.get.mockRejectedValueOnce(new Error('Offline'))
    render(<ReaderModal {...props()} />); load()
    fireEvent.click(screen.getByRole('button', { name: 'Notes (0)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
    expect(screen.getByRole('button', { name: 'Comment' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
  })
  it('shows existing marks for the current view and keeps changed quotes in the notebook', async () => {
    api.get.mockResolvedValue({ annotations: [
      { id: 'a', kind: 'underline', view: 'pages', page: 1, quote: { exact: 'Hello', prefix: '', suffix: '', start: 0 }, text: '' },
      { id: 'b', kind: 'highlight', view: 'pages', page: 1, quote: { exact: 'Gone', prefix: '', suffix: '', start: 0 }, text: '' },
      { id: 'c', kind: 'comment', view: 'text', page: 1, quote: null, text: 'Text view only' },
    ] })
    render(<ReaderModal {...props()} />); const { doc } = load()
    await waitFor(() => expect(doc.querySelector('[data-reader-note="a"]')).not.toBeNull())
    fireEvent.click(screen.getByRole('button', { name: 'Notes (2)' }))
    expect(screen.getByText('The text has changed. Your saved quote is kept here.')).toBeInTheDocument()
    expect(screen.queryByText('Text view only')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'underline · Page 1' }))
    await act(async () => { await new Promise((r) => setTimeout(r, 120)) })
  })
  it('does not fetch notes or allow writes without paid access', () => {
    render(<ReaderModal {...props()} canAnnotate={false} />); load()
    expect(api.get).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Comment' })).toBeDisabled()
  })
})
