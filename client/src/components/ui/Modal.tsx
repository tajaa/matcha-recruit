import { useEffect, useRef, type ReactNode } from 'react'

type ModalProps = {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  width?: 'sm' | 'md' | 'lg' | 'xl'
  /** Skip the default zinc-900/rounded-2xl chrome + title — children own the
   *  entire panel (their own bg/border/header). Still gets the shared
   *  backdrop + Escape-to-close + click-outside-to-close behavior below. */
  bare?: boolean
  /**
   * Whether Escape and backdrop clicks close the dialog. Default true.
   *
   * Pass `false` while an irreversible action is in flight. Several dialogs
   * migrated onto this component previously had an X button ONLY, so there was
   * no way to dismiss them by accident; adopting the shared modal handed them
   * Escape-and-click-outside for free, which is right for a form and wrong for
   * a newsletter mid-send — the dialog vanishes, the send continues, and the
   * admin is left with no confirmation either way. The explicit close control
   * stays active regardless: this governs the ACCIDENTAL dismissals only.
   */
  dismissible?: boolean
}

const widthClass = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
} as const

// Escape must close only the TOPMOST dialog. Each Modal used to register its
// own document listener, so with a confirm dialog stacked over an editor a
// single Escape fired both handlers and collapsed the whole stack. A shared
// stack of the open, dismissible modals lets the handler pick the last one.
const modalStack: Array<() => void> = []

export function Modal({
  open,
  onClose,
  title,
  children,
  width = 'md',
  bare = false,
  dismissible = true,
}: ModalProps) {
  // Held in a ref so re-registering on every onClose identity change isn't
  // needed — the stack entry stays stable for the modal's lifetime.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open || !dismissible) return
    const entry = () => onCloseRef.current()
    modalStack.push(entry)

    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // Only the top of the stack reacts, and only once per keypress.
      if (modalStack[modalStack.length - 1] !== entry) return
      e.stopPropagation()
      entry()
    }
    document.addEventListener('keydown', handler)
    return () => {
      document.removeEventListener('keydown', handler)
      const i = modalStack.indexOf(entry)
      if (i !== -1) modalStack.splice(i, 1)
    }
  }, [open, dismissible])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={(e) => {
        if (dismissible && e.target === e.currentTarget) onClose()
      }}
    >
      {bare ? children : (
        <div className={`bg-zinc-900 border border-zinc-800 rounded-2xl p-6 w-full ${widthClass[width]} shadow-xl`}>
          <h2 className="text-lg font-semibold text-zinc-100 mb-4">{title}</h2>
          {children}
        </div>
      )}
    </div>
  )
}
