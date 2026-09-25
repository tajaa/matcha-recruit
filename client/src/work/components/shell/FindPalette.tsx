import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import { ensureSearchCatalog, rankSearch, useSearchIndex, type SearchItem } from '../../utils/searchIndex'
import { openProjectFile } from '../../utils/openProjectFile'

export default function FindPalette({ userId, base }: { userId: string | undefined; base: string }) {
  const navigate = useNavigate()
  const index = useSearchIndex(userId)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const [fileError, setFileError] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const results = rankSearch(index.items, query).slice(0, 30)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
      } else if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (!open) return
    input.current?.focus()
    if (userId && !index.ready) void ensureSearchCatalog(userId)
  }, [open, userId, index.ready])

  function choose(item: SearchItem) {
    setOpen(false)
    setQuery('')
    if (item.kind === 'file') {
      if (item.projectId) void openProjectFile(item.projectId, item.id).then((opened) => { if (!opened) setFileError(true) })
      return
    }
    const path = item.kind === 'project' ? `${base}/projects/${item.id}`
      : item.kind === 'channel' ? `${base}/channels/${item.id}`
        : item.kind === 'journal' ? `${base}/journals/${item.id}` : `${base}/${item.id}`
    navigate(path)
  }

  return <>
    <button onClick={() => { setFileError(false); setOpen(true) }} title="Find (⌘K)" aria-label="Find" className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-w-dim hover:bg-w-surface2 hover:text-w-text"><Search size={15} /><span className="hidden sm:inline">Find</span><kbd className="hidden rounded border border-w-line px-1 text-[10px] sm:inline">⌘K</kbd></button>
    {fileError && <span role="alert" className="text-xs text-red-400">File unavailable</span>}
    {open && <div className="fixed inset-0 z-[95] flex justify-center bg-black/70 px-4 pt-[12vh]" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section role="dialog" aria-modal="true" aria-label="Find work" className="h-fit max-h-[70vh] w-full max-w-xl overflow-hidden rounded-xl border border-w-line bg-w-surface shadow-2xl">
        <div className="flex items-center gap-2 border-b border-w-line px-4 py-3"><Search size={17} className="text-w-faint" /><input ref={input} value={query} onChange={(event) => { setQuery(event.target.value); setSelected(0) }} onKeyDown={(event) => {
          if (event.key === 'ArrowDown') { event.preventDefault(); setSelected((value) => Math.max(0, Math.min(results.length - 1, value + 1))) }
          if (event.key === 'ArrowUp') { event.preventDefault(); setSelected((value) => Math.max(0, value - 1)) }
          if (event.key === 'Enter' && results[selected]) { event.preventDefault(); choose(results[selected]) }
        }} placeholder="Find threads, channels, projects, journals, files…" aria-label="Search work" className="min-w-0 flex-1 bg-transparent text-sm text-w-text outline-none" /><button onClick={() => setOpen(false)} aria-label="Close Find"><X size={16} /></button></div>
        <div className="max-h-[55vh] overflow-y-auto p-2">
          {!query.trim() ? <p className="px-3 py-5 text-center text-xs text-w-faint">Type to search your work.</p> : results.length === 0 ? <p className="px-3 py-5 text-center text-xs text-w-faint">No matches</p> : results.map((item, position) => <button key={`${item.kind}:${item.id}`} onMouseEnter={() => setSelected(position)} onClick={() => choose(item)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm ${selected === position ? 'bg-w-accent/15 text-w-text' : 'text-w-dim hover:bg-w-surface2'}`}><span className="min-w-0 flex-1 truncate">{item.title}</span><span className="text-[10px] capitalize text-w-faint">{item.kind}</span></button>)}
        </div>
      </section>
    </div>}
  </>
}
