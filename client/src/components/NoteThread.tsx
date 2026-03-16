import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Badge, Button, Textarea, Select, type BadgeVariant } from './ui'

type Note = {
  id: string
  note_type: string
  content: string
  created_at: string
}

type NoteThreadProps = {
  endpoint: string
  noteTypes?: { value: string; label: string; variant?: BadgeVariant }[]
  maxHeight?: string
}

const defaultNoteTypes: { value: string; label: string; variant?: BadgeVariant }[] = [
  { value: 'general', label: 'General' },
]

export function NoteThread({
  endpoint,
  noteTypes = defaultNoteTypes,
  maxHeight = 'max-h-96',
}: NoteThreadProps) {
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(true)
  const [content, setContent] = useState('')
  const [noteType, setNoteType] = useState(noteTypes[0]?.value ?? 'general')
  const [posting, setPosting] = useState(false)

  useEffect(() => {
    api.get<Note[]>(endpoint)
      .then(setNotes)
      .catch(() => setNotes([]))
      .finally(() => setLoading(false))
  }, [endpoint])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!content.trim()) return
    setPosting(true)
    try {
      const note = await api.post<Note>(endpoint, {
        note_type: noteType,
        content: content.trim(),
      })
      setNotes((prev) => [...prev, note])
      setContent('')
    } finally {
      setPosting(false)
    }
  }

  function badgeForType(type: string) {
    const def = noteTypes?.find((t) => t.value === type)
    if (!def || type === 'general') return null
    return <Badge variant={def.variant ?? 'neutral'}>{def.label}</Badge>
  }

  return (
    <div>
      {loading ? (
        <p className="text-xs text-zinc-500">Loading notes...</p>
      ) : notes.length === 0 ? (
        <p className="text-xs text-zinc-500 mb-4">No notes yet.</p>
      ) : (
        <div className={`space-y-3 mb-4 ${maxHeight} overflow-y-auto`}>
          {notes.map((n) => (
            <div key={n.id} className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] text-zinc-500">
                  {new Date(n.created_at).toLocaleString()}
                </span>
                {badgeForType(n.note_type)}
              </div>
              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{n.content}</p>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-3">
        <Textarea
          label=""
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Add a note..."
          className="min-h-[60px]"
        />
        <div className="flex items-end gap-2">
          {noteTypes && noteTypes.length > 1 && (
            <Select
              label=""
              options={noteTypes.map((t) => ({ value: t.value, label: t.label }))}
              value={noteType}
              onChange={(e) => setNoteType(e.target.value)}
              className="w-36"
            />
          )}
          <Button type="submit" size="sm" disabled={posting || !content.trim()}>
            {posting ? 'Posting...' : 'Add Note'}
          </Button>
        </div>
      </form>
    </div>
  )
}
