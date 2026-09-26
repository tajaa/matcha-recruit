import { useEffect, useState } from 'react'
import { searchInvitableUsers } from '../../api/channels'
import { addJournalCollaborators, listJournalCollaborators, removeJournalCollaborator, type Journal, type JournalCollaborator } from '../../api/matchaWork/journals'

type User = { id: string; name: string; email: string }

export default function CollaboratorsModal({ journal, userId, onClose, onChanged }: { journal: Journal; userId: string | undefined; onClose: () => void; onChanged: () => void }) {
  const [members, setMembers] = useState<JournalCollaborator[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<User[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const owner = journal.created_by === userId

  useEffect(() => { void listJournalCollaborators(journal.id).then(setMembers).catch((cause: unknown) => setError(String(cause))) }, [journal.id])
  useEffect(() => {
    if (!owner) return
    let active = true
    const timeout = window.setTimeout(() => {
      void searchInvitableUsers(query).then((users) => {
        if (active) setResults(users.filter((user) => !members.some((member) => member.user_id === user.id)))
      }).catch((cause: unknown) => { if (active) setError(String(cause)) })
    }, 250)
    return () => { active = false; window.clearTimeout(timeout) }
  }, [query, journal.id, members, owner])

  async function invite() {
    setBusy(true)
    try {
      await addJournalCollaborators(journal.id, [...selected])
      setMembers(await listJournalCollaborators(journal.id))
      setSelected(new Set())
      setError('')
      onChanged()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not invite collaborators') }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section role="dialog" aria-modal="true" aria-label={`Collaborators for ${journal.title}`} className="w-full max-w-md rounded-xl border border-w-line bg-w-surface p-5 text-w-text">
        <div className="flex items-center justify-between"><h2 className="font-semibold">Collaborators</h2><button onClick={onClose} aria-label="Close collaborators">Close</button></div>
        <div className="mt-4 max-h-36 space-y-2 overflow-y-auto text-sm">
          {members.length === 0 && <p className="text-w-faint">Only you can see this note.</p>}
          {members.map((member) => <div key={member.user_id} className="flex items-center justify-between gap-2"><span className="truncate">{member.name} <span className="text-w-faint">{member.email}</span></span>{owner && <button onClick={() => void removeJournalCollaborator(journal.id, member.user_id).then(async () => { setMembers(await listJournalCollaborators(journal.id)); onChanged() }).catch((cause: unknown) => setError(String(cause)))} className="text-xs text-red-400">Remove</button>}</div>)}
        </div>
        {owner && <>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name or email" className="mt-4 w-full rounded-md border border-w-line bg-w-surface2 px-3 py-2 text-sm" />
          <div className="mt-2 max-h-40 overflow-y-auto">
            {results.map((user) => <label key={user.id} className="flex cursor-pointer items-center gap-2 px-2 py-1.5 text-sm hover:bg-w-surface2"><input type="checkbox" checked={selected.has(user.id)} onChange={() => setSelected((previous) => { const next = new Set(previous); if (next.has(user.id)) next.delete(user.id); else next.add(user.id); return next })} /><span className="truncate">{user.name} <span className="text-w-faint">{user.email}</span></span></label>)}
          </div>
          <button onClick={() => void invite()} disabled={busy || selected.size === 0} className="mt-3 rounded-md bg-w-accent px-3 py-2 text-sm font-medium text-black disabled:opacity-50">Invite {selected.size || ''}</button>
        </>}
        {error && <p role="alert" className="mt-2 text-xs text-red-400">{error}</p>}
      </section>
    </div>
  )
}
