import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { onAuthReset } from '../../api/authReset'
import { deleteMyResume, getMyResume, updateMyResumeText, uploadMyResume, type MyResume } from '../../api/profileResume'
import { useMe } from '../../hooks/useMe'

// The person's saved résumé, shared by everything that shows it (Tasks'
// Résumé row and view, a job search form's drop-in), so a résumé dropped into
// a chat form shows in Tasks at once. Owner-scoped, cleared on logout.

type State = { owner: string; loaded: boolean; resume: MyResume | null; error: string | null }

let state: State | null = null
const listeners = new Set<() => void>()
const set = (next: State | null) => { state = next; for (const listener of listeners) listener() }
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
onAuthReset(() => set(null))

async function load(owner: string) {
  set({ owner, loaded: false, resume: state?.owner === owner ? state.resume : null, error: null })
  try {
    const resume = await getMyResume()
    if (state?.owner === owner) set({ owner, loaded: true, resume, error: null })
  } catch {
    if (state?.owner === owner) set({ owner, loaded: true, resume: null, error: "Couldn't load your résumé." })
  }
}

export const RESUME_ACCEPT = '.pdf,.docx,.doc,.txt'
export const RESUME_MAX_BYTES = 10 * 1024 * 1024

const EXTENSIONS = RESUME_ACCEPT.split(',')

/** Why a file can't be a résumé, or null. The server checks again. */
export function resumeFileProblem(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) return 'A résumé has to be a PDF, Word or text file.'
  if (file.size > RESUME_MAX_BYTES) return 'That file is over 10 MB.'
  if (file.size === 0) return 'That file is empty.'
  return null
}

export function useMyResume(enabled = true) {
  const { me } = useMe()
  const owner = me?.user?.id
  const snap = useSyncExternalStore(subscribe, () => (owner && state?.owner === owner ? state : null), () => null)

  useEffect(() => {
    if (enabled && owner && state?.owner !== owner) void load(owner)
  }, [enabled, owner])

  /** Each change sets the saved résumé to what the server returned. Throws
   *  what the server said, for the caller to show. */
  const change = useCallback(async (work: () => Promise<MyResume | null>) => {
    if (!owner) return null
    const resume = await work()
    if (state === null || state.owner === owner) set({ owner, loaded: true, resume, error: null })
    return resume
  }, [owner])

  return {
    resume: snap?.resume ?? null,
    loaded: !!snap?.loaded,
    error: snap?.error ?? null,
    reload: () => (owner ? load(owner) : Promise.resolve()),
    upload: (file: File) => change(() => uploadMyResume(file)),
    saveText: (text: string) => change(() => updateMyResumeText(text)),
    remove: () => change(async () => { await deleteMyResume(); return null }),
  }
}
