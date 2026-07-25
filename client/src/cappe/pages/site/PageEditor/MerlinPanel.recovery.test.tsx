// A turn whose ops were persisted server-side (migration zzzzcappe24) but
// never reached this client — a disconnect between the agent loop finishing
// and the SSE result frame arriving. The panel must offer to apply it, and
// only while `results` is unset (a normal completed turn always has it, even
// if empty).
// Run:  npm run test:run -- MerlinPanel.recovery
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MerlinDrawer } from './MerlinPanel'
import type { MerlinMessage } from './useMerlin'
import type { useMerlin } from './useMerlin'

vi.mock('./DesignPrimitives', () => ({ usePremium: () => true }))
vi.mock('./AssetLibrary', () => ({ AssetLibrary: () => null }))

const applyRecoveredOps = vi.fn()

const unrecovered: MerlinMessage = {
  id: 'msg-1',
  role: 'assistant',
  content: 'Darkened the hero.',
  ops: [{ op: 'set_field', block: 'b1', path: 'heading', value: 'New' }],
}

const merlinWith = (messages: MerlinMessage[]) => ({
  open: true,
  setOpen: vi.fn(),
  messages,
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
  addAttachments: vi.fn(),
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
  applyRecoveredOps,
} as unknown as ReturnType<typeof useMerlin>)

beforeEach(() => {
  Element.prototype.scrollTo = vi.fn()
  applyRecoveredOps.mockReset()
})

describe('unrecovered turn', () => {
  it('offers to apply ops that never reached the client', () => {
    render(<MerlinDrawer merlin={merlinWith([unrecovered])} selectedLabel={null} />)
    expect(screen.getByText(/Apply these changes/)).toBeTruthy()
  })

  it('calls applyRecoveredOps with the message id and its ops on click', () => {
    render(<MerlinDrawer merlin={merlinWith([unrecovered])} selectedLabel={null} />)
    fireEvent.click(screen.getByText(/Apply these changes/))
    expect(applyRecoveredOps).toHaveBeenCalledTimes(1)
    expect(applyRecoveredOps).toHaveBeenCalledWith('msg-1', unrecovered.ops)
  })

  it('does not offer to apply once results are present (a normal completed turn)', () => {
    const completed: MerlinMessage = { ...unrecovered, results: [{ ok: true, summary: 'Edited Hero — heading' }] }
    render(<MerlinDrawer merlin={merlinWith([completed])} selectedLabel={null} />)
    expect(screen.queryByText(/Apply these changes/)).toBeNull()
  })

  it('does not offer to apply a message with no ops at all', () => {
    const plain: MerlinMessage = { id: 'msg-2', role: 'assistant', content: 'Done.', results: [] }
    render(<MerlinDrawer merlin={merlinWith([plain])} selectedLabel={null} />)
    expect(screen.queryByText(/Apply these changes/)).toBeNull()
  })
})
