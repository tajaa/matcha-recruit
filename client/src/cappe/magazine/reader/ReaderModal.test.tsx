import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import ReaderModal from './ReaderModal'
import type { ReaderAnnotationBody } from './annotationTypes'
import { discardCommentDrafts } from './commentDraft'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../../api', () => ({ cappeApi: api }))
let nextAccount = 0
const props = () => ({ accountId: `reader-${++nextAccount}`, html: '<article class="mz-story"><p>Hello world</p></article>', title: 'Coast',
  endpoint: '/reader/magazines/salt/stories/coast/annotations', canAnnotate: true, asText: false,
  prepare: vi.fn(), onLink: vi.fn(), onClose: vi.fn(), onTextView: vi.fn() })

beforeEach(() => {
  api.get.mockResolvedValue({ annotations: [] })
  api.put.mockImplementation((path: string, body: ReaderAnnotationBody) => Promise.resolve({ ...body, id: path.split('/').at(-1) }))
  api.delete.mockResolvedValue({ deleted: true })
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterEach(() => {
  for (let id = 1; id <= nextAccount; id++) discardCommentDrafts(`reader-${id}`)
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

  it.each(['Highlight', 'Underline'])('keeps an unsaved comment when saving a %s', async (kind) => {
    render(<ReaderModal {...props()} />)
    const { doc } = load(); await select(doc)
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on selected words'), { target: { value: 'Keep my comment 🌍' } })
    fireEvent.click(screen.getByRole('button', { name: kind }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (1)' })).toBeInTheDocument())
    expect(screen.getByDisplayValue('Keep my comment 🌍')).toBeInTheDocument()
    expect(api.put.mock.calls[0][1].kind).toBe(kind.toLowerCase())
  })

  it('keeps text typed while a comment save is pending and saves it with a new UUID', async () => {
    render(<ReaderModal {...props()} />); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'First version' } })
    let finish!: () => void
    api.put.mockImplementationOnce((path: string, body: ReaderAnnotationBody) => new Promise((resolve) => {
      finish = () => resolve({ ...body, id: path.split('/').at(-1) })
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'First version plus newer words' } })
    await act(async () => { finish() })
    expect(screen.getByDisplayValue('First version plus newer words')).toBeInTheDocument()
    expect(screen.getByText('First version')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(screen.queryByLabelText('Comment on page 1')).not.toBeInTheDocument())
    expect(api.put.mock.calls[1][0]).not.toBe(api.put.mock.calls[0][0])
    expect(api.put.mock.calls[1][1].text).toBe('First version plus newer words')
  })

  it('warns on refresh or tab close only while a comment is unsaved', async () => {
    const showUnload = () => {
      const event = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(event)
      return event.defaultPrevented
    }
    render(<ReaderModal {...props()} />); load()
    expect(showUnload()).toBe(false)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Unsaved comment' } })
    expect(showUnload()).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(showUnload()).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Save this one' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(screen.queryByLabelText('Comment on page 1')).not.toBeInTheDocument())
    expect(showUnload()).toBe(false)
  })

  it('recovers a failed comment and its retry UUID after history Back and Forward', async () => {
    const p = props()
    let go!: (delta: number) => void
    function History() {
      const navigate = useNavigate()
      useEffect(() => { go = navigate }, [navigate])
      return null
    }
    render(<MemoryRouter initialEntries={['/magazine', '/story']} initialIndex={1}><History /><Routes>
      <Route path="/magazine" element={<p>Magazine stories</p>} />
      <Route path="/story" element={<ReaderModal {...p} />} />
    </Routes></MemoryRouter>); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Keep this after Back' } })
    api.put.mockRejectedValueOnce(new Error('Response lost'))
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost')
    await act(async () => { go(-1) })
    expect(screen.getByText('Magazine stories')).toBeInTheDocument()
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    await act(async () => { go(1) }); load()
    expect(screen.getByDisplayValue('Keep this after Back')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(screen.queryByLabelText('Comment on page 1')).not.toBeInTheDocument())
    expect(api.put.mock.calls[1][0]).toBe(api.put.mock.calls[0][0])
    await act(async () => { go(-1); }); await act(async () => { go(1) })
    expect(screen.queryByDisplayValue('Keep this after Back')).not.toBeInTheDocument()
  })

  it('leaves a recovered draft confirmable when an earlier save finishes after unmount', async () => {
    const p = props()
    const first = render(<ReaderModal {...p} />); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Save before Back' } })
    let finish!: () => void
    api.put.mockImplementationOnce((path: string, body: ReaderAnnotationBody) => new Promise((resolve) => {
      finish = () => resolve({ ...body, id: path.split('/').at(-1) })
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    first.unmount()
    render(<ReaderModal {...p} />); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save comment' })).toBeEnabled())
    await act(async () => { finish() })
    expect(screen.getByDisplayValue('Save before Back')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (1)' })).toBeInTheDocument())
    expect(api.put.mock.calls[1][0]).toBe(api.put.mock.calls[0][0])
    expect(screen.queryByLabelText('Comment on page 1')).not.toBeInTheDocument()
  })

  it('keeps a failed comment UUID through a successful unrelated mark', async () => {
    render(<ReaderModal {...props()} />)
    const { doc } = load(); await select(doc)
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on selected words'), { target: { value: 'Retry this comment' } })
    api.put.mockRejectedValueOnce(new Error('Response lost'))
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost')
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (1)' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (2)' })).toBeInTheDocument())
    expect(api.put.mock.calls[2][0]).toBe(api.put.mock.calls[0][0])
    expect(api.put.mock.calls[1][0]).not.toBe(api.put.mock.calls[0][0])
  })

  it('keeps a failed mark UUID when an unrelated comment is canceled', async () => {
    render(<ReaderModal {...props()} />)
    const { doc } = load(); await select(doc)
    api.put.mockRejectedValueOnce(new Error('Response lost'))
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost')
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on selected words'), { target: { value: 'Unrelated draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notes (1)' })).toBeInTheDocument())
    expect(api.put.mock.calls[1][0]).toBe(api.put.mock.calls[0][0])
  })

  it('isolates recovered drafts by account, story and view, and discards them explicitly', async () => {
    const p = props()
    let mounted = render(<ReaderModal {...p} />); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Account-private draft' } })
    mounted.unmount()
    for (const other of [{ accountId: 'another-reader' }, { endpoint: `${p.endpoint}-other` }, { asText: true }]) {
      mounted = render(<ReaderModal {...p} {...other} />); load()
      expect(screen.queryByDisplayValue('Account-private draft')).not.toBeInTheDocument()
      mounted.unmount()
    }
    mounted = render(<ReaderModal {...p} />); load()
    expect(screen.getByDisplayValue('Account-private draft')).toBeInTheDocument()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Close reader' }))
    expect(p.onClose).toHaveBeenCalledOnce()
    mounted.unmount()
    render(<ReaderModal {...p} />); load()
    expect(screen.queryByDisplayValue('Account-private draft')).not.toBeInTheDocument()
  })

  it('keeps a recovered draft when access is unavailable but prevents saving it', async () => {
    const p = props()
    const mounted = render(<ReaderModal {...p} />); load()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Comment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    fireEvent.change(screen.getByLabelText('Comment on page 1'), { target: { value: 'Awaiting access' } })
    mounted.unmount()
    render(<ReaderModal {...p} canAnnotate={false} />); load()
    expect(screen.getByDisplayValue('Awaiting access')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save comment' })).toBeDisabled()
    fireEvent.submit(screen.getByLabelText('Comment on page 1').closest('form')!)
    expect(api.put).not.toHaveBeenCalled()
  })
})
