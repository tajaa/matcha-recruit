import { useState } from 'react'
import type { ContactInput } from '../../api/matchaWork/sales'
import { ImportError, parseContacts } from './salesLogic'

/** Paste emails (one per line) or a CSV/TSV with a header row. Anyone marked
 *  do-not-contact and anyone already in the campaign is skipped by the server. */
export default function ImportBox({ busy, onImport }: {
  busy: boolean
  onImport: (contacts: ContactInput[]) => Promise<{ added: number; duplicates: number; suppressed: number } | null>
}) {
  const [text, setText] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)

  async function submit() {
    setProblem(null)
    setResult(null)
    let contacts: ContactInput[]
    try {
      contacts = parseContacts(text)
    } catch (e) {
      setProblem(e instanceof ImportError ? e.message : "Couldn't read that list.")
      return
    }
    const out = await onImport(contacts)
    if (!out) return
    setText('')
    const skipped = [
      out.duplicates ? `${out.duplicates} already in the campaign` : '',
      out.suppressed ? `${out.suppressed} asked not to be contacted` : '',
    ].filter(Boolean)
    setResult(`Added ${out.added}.${skipped.length ? ` Skipped ${skipped.join(', ')}.` : ''}`)
  }

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => { setText(e.target.value); setProblem(null) }}
        rows={5}
        aria-label="Contacts to import"
        placeholder={'ana@example.com\n\nor a CSV:\nemail,name,company,website\nana@example.com,Ana Ruiz,Acme Dental,acmedental.example'}
        className="w-full rounded-md border border-w-line bg-w-surface2/50 px-2.5 py-1.5 font-mono text-[11px] text-w-text outline-none focus:border-w-accent/60"
      />
      {problem && <p role="alert" className="text-[11px] text-red-400">{problem}</p>}
      {result && <p className="text-[11px] text-w-dim">{result}</p>}
      <button type="button" onClick={() => void submit()} disabled={busy || !text.trim()}
        className="rounded-md border border-w-line px-3 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2 disabled:opacity-40">
        Import contacts
      </button>
    </div>
  )
}
