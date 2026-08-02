// Sticky selection UX (2026-08-01): the coarse "Working on X" chip must be
// dismissable, and a pending section switch ("Work on Y instead?") must offer
// Switch / keep rather than silently repointing. Run:
//   npm run test:run -- MerlinPanel.selection
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MerlinDrawer } from './MerlinPanel'
import type { useMerlin } from './useMerlin'

vi.mock('./DesignPrimitives', () => ({ usePremium: () => true }))
vi.mock('./AssetLibrary', () => ({ AssetLibrary: () => null }))

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
} as unknown as ReturnType<typeof useMerlin>)

const originalScrollTo = Element.prototype.scrollTo

beforeEach(() => {
  // jsdom has no layout, so the transcript's scroll-to-bottom effect throws.
  Element.prototype.scrollTo = vi.fn()
})

afterEach(() => {
  Element.prototype.scrollTo = originalScrollTo
})

// Text is split across nodes ("Working on " <strong>Hero</strong> " — what...")
// — match the innermost <span> wrapper by aggregate textContent rather than
// exact node text. Scoped to `span` so ancestor divs (which also "contain"
// the text) don't trip getByText's single-match requirement.
const findByTextContent = (needle: string) =>
  screen.getByText(
    (_content, node) => node?.tagName === 'SPAN' && (node?.textContent ?? '').includes(needle),
  )

describe('coarse selection chip', () => {
  it('has no clear button when onClearSelected is not provided', () => {
    render(<MerlinDrawer merlin={merlin()} selectedLabel="Hero" />)
    findByTextContent('Working on Hero')
    expect(screen.queryByTitle('Clear selection')).toBeNull()
  })

  it('renders a clear button when onClearSelected is provided, and fires it', () => {
    const onClearSelected = vi.fn()
    render(<MerlinDrawer merlin={merlin()} selectedLabel="Hero" onClearSelected={onClearSelected} />)
    fireEvent.click(screen.getByTitle('Clear selection'))
    expect(onClearSelected).toHaveBeenCalledTimes(1)
  })

  it('the fine-grained selectionChip clear still wins over onClearSelected', () => {
    const onClear = vi.fn()
    const onClearSelected = vi.fn()
    render(
      <MerlinDrawer
        merlin={merlin()}
        selectedLabel="Hero"
        selectionChip={{ label: 'Hero heading', onClear }}
        onClearSelected={onClearSelected}
      />,
    )
    fireEvent.click(screen.getByTitle('Clear selection'))
    expect(onClear).toHaveBeenCalledTimes(1)
    expect(onClearSelected).not.toHaveBeenCalled()
  })
})

describe('pending selection (sticky switch)', () => {
  it('renders nothing when there is no pending switch', () => {
    render(<MerlinDrawer merlin={merlin()} selectedLabel="Hero" />)
    expect(screen.queryByText('Switch')).toBeNull()
    expect(screen.queryByTitle('Keep current selection')).toBeNull()
  })

  it('renders "Work on X instead?" with Switch and a keep (✕) button', () => {
    const onConfirm = vi.fn()
    const onDismiss = vi.fn()
    render(
      <MerlinDrawer
        merlin={merlin()}
        selectedLabel="Hero"
        pendingChip={{ label: 'Text', onConfirm, onDismiss }}
      />,
    )
    findByTextContent('Work on Text instead?')
    fireEvent.click(screen.getByText('Switch'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('the keep button dismisses the pending switch without touching the active chip', () => {
    const onConfirm = vi.fn()
    const onDismiss = vi.fn()
    render(
      <MerlinDrawer
        merlin={merlin()}
        selectedLabel="Hero"
        pendingChip={{ label: 'Text', onConfirm, onDismiss }}
      />,
    )
    fireEvent.click(screen.getByTitle('Keep current selection'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('both the pending row and the active chip render together', () => {
    render(
      <MerlinDrawer
        merlin={merlin()}
        selectedLabel="Hero"
        pendingChip={{ label: 'Text', onConfirm: vi.fn(), onDismiss: vi.fn() }}
      />,
    )
    findByTextContent('Work on Text instead?')
    findByTextContent('Working on Hero')
  })
})
