import { createContext, useCallback, useContext, useState } from 'react'
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface ToastOptions {
  type?: ToastType
  onClick?: () => void
  duration?: number // ms; default 3000
}

interface Toast {
  id: number
  message: string
  type: ToastType
  onClick?: () => void
}

interface ToastContextValue {
  toast: (message: string, typeOrOptions?: ToastType | ToastOptions) => void
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

let _nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((message: string, typeOrOptions: ToastType | ToastOptions = 'success') => {
    const id = ++_nextId
    const options: ToastOptions =
      typeof typeOrOptions === 'string' ? { type: typeOrOptions } : typeOrOptions
    const type = options.type ?? 'success'
    const duration = options.duration ?? 3000
    setToasts(prev => [...prev, { id, message, type, onClick: options.onClick }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration)
  }, [])

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const icons = { success: CheckCircle, error: AlertCircle, info: Info }
  const colors = {
    success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    error: 'border-red-500/30 bg-red-500/10 text-red-300',
    info: 'border-blue-500/30 bg-blue-500/10 text-blue-300',
  }

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => {
          const Icon = icons[t.type]
          const clickable = !!t.onClick
          return (
            <div
              key={t.id}
              onClick={() => {
                if (clickable) {
                  t.onClick?.()
                  dismiss(t.id)
                }
              }}
              className={`pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded-lg border text-xs font-medium shadow-lg backdrop-blur-sm animate-in slide-in-from-right ${colors[t.type]} ${clickable ? 'cursor-pointer hover:brightness-110' : ''}`}
              style={{ animation: 'slideIn 0.2s ease-out' }}
            >
              <Icon size={14} />
              <span className="flex-1">{t.message}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  dismiss(t.id)
                }}
                className="opacity-50 hover:opacity-100"
              >
                <X size={12} />
              </button>
            </div>
          )
        })}
      </div>
      <style>{`
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      `}</style>
    </ToastContext.Provider>
  )
}
