import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

/**
 * Right-side slide-in panel for detail views (statute text, record detail).
 * Lifted from the KeyCoverageDrawer shell into a shared primitive.
 */
export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  width = 'lg',
  children,
}: {
  open: boolean
  onClose: () => void
  title?: ReactNode
  subtitle?: ReactNode
  width?: 'md' | 'lg' | 'xl'
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  const w = width === 'xl' ? 'max-w-3xl' : width === 'md' ? 'max-w-xl' : 'max-w-2xl'

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className={`relative ml-auto flex h-full w-full ${w} flex-col overflow-hidden border-l border-zinc-700 bg-zinc-900 shadow-2xl`}>
        <div className="flex items-start justify-between border-b border-zinc-700/50 px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="truncate text-lg font-semibold text-zinc-100">{title}</h2>}
            {subtitle && <div className="mt-0.5 text-xs text-zinc-500">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="ml-3 shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  )
}

export default Drawer
