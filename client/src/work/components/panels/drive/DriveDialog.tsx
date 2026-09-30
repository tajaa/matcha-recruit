import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Modal } from '../../../../components/ui/Modal'

// Shared Modal behavior (Escape, click-outside, stacking) with work-theme
// chrome — the default Modal panel is the matcha zinc palette.
export default function DriveDialog({ title, onClose, dismissible = true, children }: {
  title: string
  onClose: () => void
  dismissible?: boolean
  children: ReactNode
}) {
  return (
    <Modal open onClose={onClose} bare dismissible={dismissible}>
      <div role="dialog" aria-label={title} className="mx-4 w-full max-w-md rounded-2xl border border-w-line bg-w-surface p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="truncate text-base font-semibold text-w-text">{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-md p-1 text-w-faint hover:text-w-text">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </Modal>
  )
}
