import { useEffect, useRef, useState } from 'react'
import { Settings, Volume2, MessageSquare } from 'lucide-react'
import { useNotificationSettings } from '../../hooks/useNotificationSettings'

export default function NotificationSettingsMenu() {
  const [open, setOpen] = useState(false)
  const { sound, toast, setSound, setToast } = useNotificationSettings()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-zinc-400 hover:text-white p-1 rounded transition-colors"
        title="Notification settings"
        aria-label="Notification settings"
      >
        <Settings size={16} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-64 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl z-50 text-xs">
          <div className="px-3 py-2 border-b border-zinc-800 text-zinc-400 font-medium">
            Channel notifications
          </div>
          <Toggle
            icon={<Volume2 size={14} />}
            label="Sound on new message"
            value={sound}
            onChange={setSound}
          />
          <Toggle
            icon={<MessageSquare size={14} />}
            label="Toast popup on new message"
            value={toast}
            onChange={setToast}
          />
          <div className="px-3 py-2 border-t border-zinc-800 text-[10px] text-zinc-500">
            Notifications fire for channels you&apos;re a member of, except the one you&apos;re currently viewing.
          </div>
        </div>
      )}
    </div>
  )
}

function Toggle({
  icon,
  label,
  value,
  onChange,
}: {
  icon: React.ReactNode
  label: string
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      onClick={() => onChange(!value)}
      className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-zinc-800/60 text-left"
    >
      <span className="text-zinc-400">{icon}</span>
      <span className="flex-1 text-zinc-200">{label}</span>
      <span
        className={`inline-block w-8 h-4 rounded-full relative transition-colors ${
          value ? 'bg-emerald-500' : 'bg-zinc-700'
        }`}
      >
        <span
          className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
            value ? 'translate-x-4' : 'translate-x-0.5'
          }`}
        />
      </span>
    </button>
  )
}
