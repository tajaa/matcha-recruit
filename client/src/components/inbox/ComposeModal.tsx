import { useState, useRef, useEffect, useCallback } from 'react'
import { X, Loader2 } from 'lucide-react'
import { Modal } from '../ui'
import { searchUsers, createConversation } from '../../api/inbox'
import type { UserSearchResult, Conversation } from '../../api/inbox'
import Avatar from '../Avatar'

type Props = {
  isOpen: boolean
  onClose: () => void
  onCreated: (conversation: Conversation) => void
}

export function ComposeModal({ isOpen, onClose, onCreated }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<UserSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<UserSearchResult[]>([])
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const searchTimeout = useRef<ReturnType<typeof setTimeout>>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen])

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setQuery('')
      setResults([])
      setSelected([])
      setMessage('')
      setError(null)
      setSearching(false)
      setSending(false)
    }
  }, [isOpen])

  const doSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    try {
      const users = await searchUsers(q.trim())
      setResults(users)
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }, [])

  function handleQueryChange(value: string) {
    setQuery(value)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    searchTimeout.current = setTimeout(() => doSearch(value), 300)
  }

  function addRecipient(user: UserSearchResult) {
    if (selected.some((s) => s.id === user.id)) return
    setSelected((prev) => [...prev, user])
    setQuery('')
    setResults([])
    inputRef.current?.focus()
  }

  function removeRecipient(userId: string) {
    setSelected((prev) => prev.filter((s) => s.id !== userId))
  }

  async function handleSend() {
    if (selected.length === 0 || !message.trim()) return
    setSending(true)
    setError(null)
    try {
      const convo = await createConversation(
        selected.map((s) => s.id),
        message.trim(),
      )
      onCreated(convo)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message')
    } finally {
      setSending(false)
    }
  }

  // Filter out already-selected users from results
  const filteredResults = results.filter(
    (r) => !selected.some((s) => s.id === r.id),
  )

  return (
    <Modal open={isOpen} onClose={onClose} title="New Message" width="md">
      <div className="space-y-4">
        {/* Recipients */}
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1.5">To</label>
          <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-2 min-h-[42px] flex flex-wrap items-center gap-1.5">
            {selected.map((user) => (
              <span
                key={user.id}
                className="inline-flex items-center gap-1 rounded-md bg-zinc-800 border border-zinc-700 px-2 py-1 text-xs text-zinc-200"
              >
                {user.name}
                <button
                  onClick={() => removeRecipient(user.id)}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
            <div className="relative flex-1 min-w-[120px]">
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => handleQueryChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && filteredResults.length > 0) {
                    e.preventDefault()
                    addRecipient(filteredResults[0])
                  } else if (e.key === 'Backspace' && !query && selected.length > 0) {
                    removeRecipient(selected[selected.length - 1].id)
                  }
                }}
                placeholder={selected.length === 0 ? 'Name, or full email for external...' : 'Add another...'}
                className="w-full bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none"
              />
            </div>
          </div>

          {/* Search results dropdown */}
          {(filteredResults.length > 0 || searching) && query.trim().length >= 2 && (
            <div className="mt-1 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl max-h-[200px] overflow-y-auto">
              {searching && (
                <div className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-500">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Searching...
                </div>
              )}
              {!searching && filteredResults.length === 0 && (
                <div className="px-3 py-2.5">
                  <p className="text-sm text-zinc-500">No users found</p>
                  {!query.includes('@') && (
                    <p className="text-xs text-zinc-600 mt-1">Enter a full email address to message someone outside your organization</p>
                  )}
                </div>
              )}
              {filteredResults.map((user) => (
                <button
                  key={user.id}
                  onClick={() => addRecipient(user)}
                  className="w-full text-left px-3 py-2 hover:bg-zinc-800 transition-colors flex items-center gap-2.5"
                >
                  <Avatar name={user.name} avatarUrl={user.avatar_url} size="sm" />
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-200 truncate">{user.name}</div>
                    <div className="text-xs text-zinc-500 truncate">
                      {user.email}
                      {user.company_name && ` - ${user.company_name}`}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Message body */}
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1.5">Message</label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type your message..."
            rows={4}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors resize-y min-h-[80px]"
          />
        </div>

        {/* Error */}
        {error && (
          <p className="text-sm text-red-400">{error}</p>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={selected.length === 0 || !message.trim() || sending}
            className="rounded-lg bg-zinc-700 px-5 py-2 text-sm font-medium text-white hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-2"
          >
            {sending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Send
          </button>
        </div>
      </div>
    </Modal>
  )
}
