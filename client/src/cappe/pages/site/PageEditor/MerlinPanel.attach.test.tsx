// The screenshot→chat paths: dropping a file on the panel and pasting one with
// focus outside it must both reach the same addAttachments the paperclip uses.
// Run:  npm run test:run -- MerlinPanel.attach
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MerlinDrawer } from './MerlinPanel'
import type { useMerlin } from './useMerlin'

vi.mock('./DesignPrimitives', () => ({ usePremium: () => true }))
vi.mock('./AssetLibrary', () => ({ AssetLibrary: () => null }))

const addAttachments = vi.fn()

const merlin = () => ({
  open: true,
  setOpen: vi.fn(),
  messages: [],
  send: vi.fn(),
  sending: false,
  error: null,
  tier: 'auto',
  setTier: vi.fn(),
  width: 400,
  setWidth: vi.fn(),
  setWidthLive: vi.fn(),
  expanded: false,
  setExpanded: vi.fn(),
  newConversation: vi.fn(),
  status: null,
  liveSteps: [],
  schema: null,
  attachments: [],
  addAttachments,
  addAttachmentFromUrl: vi.fn(),
  removeAttachment: vi.fn(),
  attachmentUploading: false,
  attachmentError: null,
  conversationId: null,
  conversations: [],
  openConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  getImageTargets: () => [],
  applyImageTo: vi.fn(),
  generateImage: vi.fn(),
} as unknown as ReturnType<typeof useMerlin>)

const shot = () => new File([new Uint8Array([1, 2, 3])], 'Screenshot.png', { type: 'image/png' })
const transfer = (files: File[]) => ({ types: ['Files'], files, items: [] })

const panel = () => screen.getByText('Merlin').closest('div.relative') as HTMLElement

beforeEach(() => {
  // jsdom has no layout, so the transcript's scroll-to-bottom effect throws.
  Element.prototype.scrollTo = vi.fn()
  addAttachments.mockReset()
  render(<MerlinDrawer merlin={merlin()} selectedLabel={null} />)
})

describe('drop', () => {
  it('shows the drop affordance while a file drag is over the panel', () => {
    fireEvent.dragEnter(panel(), { dataTransfer: transfer([shot()]) })
    expect(screen.getByText('Drop to attach')).toBeTruthy()
  })

  it('attaches the dropped image', () => {
    fireEvent.drop(panel(), { dataTransfer: transfer([shot()]) })
    expect(addAttachments).toHaveBeenCalledTimes(1)
    expect(addAttachments.mock.calls[0][0]).toHaveLength(1)
  })

  it('ignores a dropped non-image', () => {
    const pdf = new File([new Uint8Array([1])], 'contract.pdf', { type: 'application/pdf' })
    fireEvent.drop(panel(), { dataTransfer: transfer([pdf]) })
    expect(addAttachments).not.toHaveBeenCalled()
  })
})

describe('paste', () => {
  it('attaches a clipboard screenshot pasted with focus outside the panel', () => {
    fireEvent.paste(document.body, {
      clipboardData: { files: [shot()], items: [], types: ['Files'] },
    })
    expect(addAttachments).toHaveBeenCalledTimes(1)
  })

  it('leaves a plain-text paste alone', () => {
    fireEvent.paste(document.body, {
      clipboardData: { files: [], items: [{ kind: 'string', getAsFile: () => null }], types: ['text/plain'] },
    })
    expect(addAttachments).not.toHaveBeenCalled()
  })
})
