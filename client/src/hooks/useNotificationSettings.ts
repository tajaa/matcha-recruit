import { useCallback, useEffect, useState } from 'react'

// localStorage-backed toggles for channel notification behaviour.
// Default: both sound and toast ON.
const SOUND_KEY = 'mw-channel-sound'
const TOAST_KEY = 'mw-channel-toast'

function readBool(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback
  const v = localStorage.getItem(key)
  if (v === null) return fallback
  return v === 'true'
}

// Module-level event bus so multiple component instances see live updates
// when one of them toggles a setting.
const listeners = new Set<() => void>()
function notify() {
  for (const fn of listeners) fn()
}

export function getChannelSoundEnabled(): boolean {
  return readBool(SOUND_KEY, true)
}

export function getChannelToastEnabled(): boolean {
  return readBool(TOAST_KEY, true)
}

export function useNotificationSettings() {
  const [sound, setSoundState] = useState(() => getChannelSoundEnabled())
  const [toast, setToastState] = useState(() => getChannelToastEnabled())

  useEffect(() => {
    const sync = () => {
      setSoundState(getChannelSoundEnabled())
      setToastState(getChannelToastEnabled())
    }
    listeners.add(sync)
    return () => {
      listeners.delete(sync)
    }
  }, [])

  const setSound = useCallback((value: boolean) => {
    localStorage.setItem(SOUND_KEY, String(value))
    notify()
  }, [])

  const setToast = useCallback((value: boolean) => {
    localStorage.setItem(TOAST_KEY, String(value))
    notify()
  }, [])

  return { sound, toast, setSound, setToast }
}
