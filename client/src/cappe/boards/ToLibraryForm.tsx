import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { CappeAsset } from '../types'
import { boardsApi, type Pin } from './api'

function message(e: unknown, fallback: string) {
  return e instanceof Error && e.message ? e.message : fallback
}

/** Make a pinned picture a library picture, so a story can use it. Asks what
 *  the library upload asks; a pinned picture is reference until then.
 *  `dark` is the Studio's look; the dashboard's is the default. */
export default function ToLibraryForm({ siteId, pin, onDone, onCancel, dark = false }: {
  siteId: string
  pin: Pin
  onDone: (pin: Pin, asset: CappeAsset) => void
  onCancel: () => void
  dark?: boolean
}) {
  const [attested, setAttested] = useState(false)
  const [aiMade, setAiMade] = useState(false)
  const [alt, setAlt] = useState(pin.alt ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const add = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await boardsApi.toLibrary(siteId, pin.board_id, pin.id,
        { rights_attested: true, ai_made: aiMade, alt: alt.trim() || undefined })
      onDone(res.pin, res.asset)
    } catch (e) {
      setError(message(e, 'That picture couldn’t be added.'))
      setBusy(false)
    }
  }

  const input = dark
    ? 'w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-emerald-500'
    : 'w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500'
  return (
    <form className={`space-y-2 ${dark ? 'text-xs' : 'text-sm'} text-zinc-300`}
      onSubmit={(e) => { e.preventDefault(); if (attested && !busy) void add() }}>
      <p className="text-zinc-400">A pinned picture is private reference. To use it in a story, add it to your library.</p>
      <label className="block">
        <span className="mb-1 block text-zinc-400">Alt text (what the picture shows)</span>
        <input value={alt} maxLength={500} onChange={(e) => setAlt(e.target.value)} className={input} />
      </label>
      <label className="flex items-start gap-2">
        <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} className="mt-0.5" />
        <span>I took this picture, or I have permission to publish it.</span>
      </label>
      <label className="flex items-start gap-2">
        <input type="checkbox" checked={aiMade} onChange={(e) => setAiMade(e.target.checked)} className="mt-0.5" />
        <span>It was made with AI (it will be credited “AI illustration”).</span>
      </label>
      {error && <p role="alert" className="text-red-300">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={!attested || busy}
          className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 font-medium text-white hover:bg-emerald-500 disabled:opacity-50">
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Add to library
        </button>
        <button type="button" onClick={onCancel} className="rounded-md px-3 py-1.5 text-zinc-400 hover:text-zinc-200">Cancel</button>
      </div>
    </form>
  )
}
