import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BookOpen, Loader2 } from 'lucide-react'
import { Logo } from '../../components/ui'
import type { PublicHandbook as PublicHandbookData } from '../../types/handbook'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// ---------------------------------------------------------------------------
// PublicHandbook — a published handbook, readable by anyone holding the link.
// No auth: the token in the URL is the credential. Renders outside every
// sidebar/auth layout (registered as a top-level route in App.tsx).
//
// Read-only by construction: there is no public PDF endpoint, so no download
// affordance exists here. Printing is suppressed too (see the @media print rule
// below) — though neither stops a determined reader from copying the text or
// taking a screenshot. The revocable token, not the UI, is the real control.
// ---------------------------------------------------------------------------

export default function PublicHandbook() {
  const { token } = useParams<{ token: string }>()
  const [data, setData] = useState<PublicHandbookData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${BASE}/shared/handbook/${token}`)
        if (cancelled) return
        if (res.status === 404) {
          setError('This handbook link is no longer available. It may have been revoked or expired.')
          return
        }
        if (!res.ok) {
          setError(`Could not load this handbook (${res.status}).`)
          return
        }
        setData(await res.json())
      } catch {
        if (!cancelled) setError('Network error. Please try again.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [token])

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-6 text-center">
        <Logo />
        <BookOpen className="h-8 w-8 text-zinc-700 mt-8 mb-3" />
        <p className="text-sm text-zinc-400 max-w-md">{error || 'Handbook not found.'}</p>
      </div>
    )
  }

  const published = data.published_at
    ? new Date(data.published_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
    : null

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Browsers can "print to PDF"; this makes the shared view a screen-only
          document, consistent with there being no download endpoint. */}
      <style>{'@media print { body { display: none !important } }'}</style>

      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-[90ch] mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-zinc-100 truncate">{data.title}</h1>
            <p className="text-xs text-zinc-500 mt-0.5 truncate">
              {data.company_name}
              {published && <> · Published {published}</>}
            </p>
          </div>
          <Logo />
        </div>
      </header>

      <main className="max-w-[90ch] mx-auto px-6 py-10 space-y-10 select-none">
        {data.sections.length === 0 && (
          <p className="text-sm text-zinc-600">This handbook has no published sections yet.</p>
        )}
        {data.sections.map((s, i) => (
          <section key={i}>
            <h2 className="text-lg font-semibold text-zinc-100 mb-2">{s.title}</h2>
            <div className="prose prose-sm prose-invert prose-zinc max-w-none text-sm leading-relaxed text-zinc-300 prose-headings:text-zinc-100 prose-p:my-2">
              <Markdown remarkPlugins={[remarkGfm]}>{s.content}</Markdown>
            </div>
          </section>
        ))}
      </main>

      <footer className="border-t border-zinc-800 py-6">
        <p className="text-center text-xs text-zinc-600">
          Shared read-only via Matcha · This document is for reference and is not a contract of employment.
        </p>
      </footer>
    </div>
  )
}
