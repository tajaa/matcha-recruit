import { useCallback, useEffect, useState } from 'react'
import { API_BASE } from '../../api/client'
import type {
  ChatMessage,
  MissingItem,
  PublicSpec,
  PublicSymlinkInfo,
  PublicTurnResponse,
  SymlinkAttachment,
} from '../../types/symlink'

// Public, unauthenticated: the per-task token is the credential, so these use
// bare fetch() (no auth interceptor). The unlock token comes back from
// /unlock and rides in this header on every later call; it is kept in
// sessionStorage keyed by the link token so a reload resumes the chat.
const UNLOCK_HEADER = 'X-Symlink-Unlock'

export type Stage =
  | 'validating'
  | 'invalid'
  | 'closed'
  | 'locked'
  | 'chat'
  | 'review'
  | 'submitting'
  | 'submitted'

function storageKey(token: string) {
  return `symlink:unlock:${token}`
}

function readUnlock(token: string): string | null {
  try {
    return sessionStorage.getItem(storageKey(token))
  } catch {
    return null
  }
}

function writeUnlock(token: string, value: string | null) {
  try {
    if (value) sessionStorage.setItem(storageKey(token), value)
    else sessionStorage.removeItem(storageKey(token))
  } catch {
    /* private mode / blocked storage — the session just won't survive a reload */
  }
}

async function readError(res: Response, fallback: string) {
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null
  return typeof body?.detail === 'string' ? body.detail : fallback
}

export function useSymLinkSession(token: string | undefined) {
  const [stage, setStage] = useState<Stage>(() => (token ? 'validating' : 'invalid'))
  const [info, setInfo] = useState<PublicSymlinkInfo | null>(null)
  const [spec, setSpec] = useState<PublicSpec | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [fields, setFields] = useState<Record<string, unknown>>({})
  const [attachments, setAttachments] = useState<SymlinkAttachment[]>([])
  const [missing, setMissing] = useState<MissingItem[]>([])
  const [complete, setComplete] = useState(false)
  const [sending, setSending] = useState(false)
  const [uploading, setUploading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [unlock, setUnlock] = useState<string | null>(() => (token ? readUnlock(token) : null))

  const headers = useCallback((extra?: Record<string, string>) => {
    const h: Record<string, string> = { ...(extra ?? {}) }
    if (unlock) h[UNLOCK_HEADER] = unlock
    return h
  }, [unlock])

  const absorb = useCallback((data: PublicSymlinkInfo) => {
    setInfo(data)
    if (data.spec) setSpec(data.spec)
    if (data.transcript) setMessages(data.transcript)
    if (data.known_fields) setFields(data.known_fields)
    if (data.attachments) setAttachments(data.attachments)
    if (data.missing) setMissing(data.missing)
    setComplete(Boolean(data.complete))
  }, [])

  useEffect(() => {
    if (!token) return  // initial stage is already 'invalid'
    let cancelled = false
    // Re-seed from storage for *this* token: /sym/A → /sym/B is a param change
    // on the same route element, not a remount, so the lazy useState above
    // would otherwise send A's unlock token for B (and then wipe B's on the
    // inevitable "not unlocked" answer).
    const stored = readUnlock(token)
    setUnlock(stored)
    setStage('validating')
    setError(null)
    const initialHeaders: Record<string, string> = stored ? { [UNLOCK_HEADER]: stored } : {}
    fetch(`${API_BASE}/sym/${token}`, { headers: initialHeaders })
      .then(async (res) => {
        if (cancelled) return
        if (!res.ok) {
          setStage('invalid')
          return
        }
        const data = (await res.json().catch(() => null)) as PublicSymlinkInfo | null
        if (!data) {
          setStage('invalid')
          return
        }
        absorb(data)
        if (!data.valid) {
          setStage('closed')
          return
        }
        if (data.unlocked) {
          setStage('chat')
        } else {
          // A stale unlock token (rotated link, revoked session) — drop it.
          if (stored) {
            writeUnlock(token, null)
            setUnlock(null)
          }
          setStage('locked')
        }
      })
      .catch(() => { if (!cancelled) setStage('invalid') })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function enterPasscode(passcode: string, honeypot = '') {
    if (!token) return
    setError(null)
    setSending(true)
    try {
      const res = await fetch(`${API_BASE}/sym/${token}/unlock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode, internal_ref: honeypot || null }),
      })
      if (!res.ok) {
        if (res.status === 410) { setStage('closed'); return }
        setError(await readError(res, res.status === 429 ? 'Too many attempts. Wait a few minutes and try again.' : 'That passcode did not work.'))
        return
      }
      const data = (await res.json()) as PublicSymlinkInfo
      if (data.unlock_token) {
        writeUnlock(token, data.unlock_token)
        setUnlock(data.unlock_token)
      }
      absorb(data)
      setStage('chat')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSending(false)
    }
  }

  async function send(text: string) {
    const content = text.trim()
    if (!content || sending || !token) return
    setMessages((m) => [...m, { role: 'user', content }])
    setSending(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/sym/${token}/chat/turn`, {
        method: 'POST',
        headers: headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ message: content }),
      })
      if (!res.ok) {
        if (res.status === 401) { setStage('locked'); return }
        if (res.status === 410) { setStage('closed'); return }
        throw new Error(res.status === 429 ? 'Too many messages. Please wait a moment.' : 'We could not continue the chat. You can review what you have.')
      }
      const result = (await res.json()) as PublicTurnResponse
      setMessages((m) => [...m, { role: 'assistant', content: result.assistant_message }])
      setFields(result.fields)
      setComplete(result.complete)
      if (result.error) setError('We could not continue the chat. You can review what you have.')
      if (result.limit_reached) setStage('review')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'We could not continue the chat.')
    } finally {
      setSending(false)
    }
  }

  async function upload(slot: string, file: File) {
    if (!token) return
    setUploading(slot)
    setError(null)
    try {
      const form = new FormData()
      form.append('slot', slot)
      form.append('file', file)
      const res = await fetch(`${API_BASE}/sym/${token}/attachments`, { method: 'POST', headers: headers(), body: form })
      if (!res.ok) {
        if (res.status === 401) { setStage('locked'); return }
        throw new Error(await readError(res, 'Upload failed.'))
      }
      const data = (await res.json()) as { attachment: SymlinkAttachment; complete: boolean; missing: MissingItem[] }
      setAttachments((list) => [...list.filter((a) => a.slot !== slot), data.attachment])
      setComplete(data.complete)
      setMissing(data.missing)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setUploading(null)
    }
  }

  async function removeAttachment(attachmentId: string) {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/sym/${token}/attachments/${attachmentId}`, { method: 'DELETE', headers: headers() })
      if (!res.ok) throw new Error(await readError(res, 'Could not remove the file.'))
      const data = (await res.json()) as { complete: boolean; missing: MissingItem[] }
      setAttachments((list) => list.filter((a) => a.id !== attachmentId))
      setComplete(data.complete)
      setMissing(data.missing)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove the file.')
    }
  }

  async function submit(finalFields: Record<string, unknown>, honeypot = '') {
    if (!token) return
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/sym/${token}/submit`, {
        method: 'POST',
        headers: headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ fields: finalFields, internal_ref: honeypot || null }),
      })
      if (!res.ok) {
        if (res.status === 410) { setStage('closed'); return }
        if (res.status === 401) { setStage('locked'); return }
        setError(await readError(res, 'Something went wrong. Please try again.'))
        setStage('review')
        return
      }
      writeUnlock(token, null)
      setStage('submitted')
    } catch {
      setError('Network error. Please try again.')
      setStage('review')
    }
  }

  return {
    stage, setStage, info, spec, messages, fields, setFields, attachments, missing, complete,
    sending, uploading, error, setError,
    enterPasscode, send, upload, removeAttachment, submit,
  }
}
