import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowLeft, CheckCircle2, Loader2 } from 'lucide-react'
import { Button, Card, Input } from '../../components/ui'
import {
  portalDocumentsApi, isHandbookDoc,
  type DocumentHandbookContent, type EmployeeDocument,
} from '../../api/portal/portalDocuments'

// ---------------------------------------------------------------------------
// EmployeeSignDocument — read an assigned handbook, then acknowledge it.
// The typed legal name is the signature (stored as `signature_data`, alongside
// the signing IP and timestamp, by POST /v1/portal/me/documents/{id}/sign).
// ---------------------------------------------------------------------------

export default function EmployeeSignDocument() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()

  const [doc, setDoc] = useState<EmployeeDocument | null>(null)
  const [content, setContent] = useState<DocumentHandbookContent | null>(null)
  // Distinct from `error` (a sign failure): the text we're asking them to
  // attest to didn't load. Signing stays blocked while this is set.
  const [contentError, setContentError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [typedName, setTypedName] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [signing, setSigning] = useState(false)

  useEffect(() => {
    if (!documentId) return
    let alive = true
    void (async () => {
      try {
        const d = await portalDocumentsApi.get(documentId)
        if (!alive) return
        setDoc(d)
        if (isHandbookDoc(d)) {
          try {
            setContent(await portalDocumentsApi.handbookContent(documentId))
          } catch (e) {
            if (alive) {
              setContentError(
                e instanceof Error ? e.message : 'Could not load this handbook’s text',
              )
            }
          }
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load this document')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [documentId])

  const sign = async () => {
    if (!documentId || !typedName.trim() || !agreed) return
    setSigning(true)
    setError(null)
    try {
      const updated = await portalDocumentsApi.sign(documentId, typedName.trim())
      setDoc(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record your signature')
    } finally {
      setSigning(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  if (!doc) return <p className="text-sm text-red-400">{error ?? 'Document not found.'}</p>

  const alreadySigned = doc.status === 'signed'
  // Never let someone attest to a handbook whose text we failed to render —
  // that's the exact thing this acknowledgement is supposed to evidence.
  const contentUnavailable = isHandbookDoc(doc) && content === null

  return (
    <div className="max-w-3xl">
      <button
        onClick={() => navigate('/portal')}
        className="text-xs text-zinc-500 hover:text-zinc-300 inline-flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="w-3.5 h-3.5" /> Back
      </button>

      <h1 className="text-2xl font-semibold text-zinc-100">{doc.title}</h1>
      {doc.description && <p className="text-sm text-zinc-500 mt-1">{doc.description}</p>}

      {content ? (
        <Card className="mt-6 p-6 max-h-[60vh] overflow-y-auto">
          <div className="space-y-8">
            {content.sections.map((s, i) => (
              <section key={i}>
                <h2 className="text-base font-semibold text-zinc-100 mb-2">{s.title}</h2>
                <div className="prose prose-sm prose-invert prose-zinc max-w-none text-sm leading-relaxed text-zinc-300 prose-headings:text-zinc-100 prose-p:my-2">
                  <Markdown remarkPlugins={[remarkGfm]}>{s.content}</Markdown>
                </div>
              </section>
            ))}
          </div>
        </Card>
      ) : contentUnavailable ? (
        <Card className="mt-6 p-5 space-y-2">
          <p className="text-sm text-amber-400">
            ⚠ We couldn't load this handbook's text{contentError ? `: ${contentError}` : '.'}
          </p>
          <p className="text-sm text-zinc-500">
            You can't sign until it loads — reload the page, or contact your HR administrator if it
            keeps failing.
          </p>
          <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>
            Retry
          </Button>
        </Card>
      ) : (
        <Card className="mt-6 p-5 text-sm text-zinc-500">
          This document has no readable text in the portal. Contact your HR administrator for a copy
          before signing.
        </Card>
      )}

      {alreadySigned ? (
        <Card className="mt-4 p-5 flex items-center gap-2 text-sm text-emerald-400">
          <CheckCircle2 className="w-4 h-4" />
          Acknowledged{doc.signed_at && <> on {new Date(doc.signed_at).toLocaleDateString()}</>}.
        </Card>
      ) : contentUnavailable ? null : (
        <Card className="mt-4 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-zinc-300">Acknowledgement</h2>
          <label className="flex items-start gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 accent-emerald-500"
            />
            <span>
              I confirm I have received, read, and understand this document, and agree to comply
              with it.
            </span>
          </label>
          <Input
            label="Type your full legal name to sign"
            value={typedName}
            onChange={(e) => setTypedName(e.target.value)}
            placeholder="Jane Doe"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <Button size="sm" onClick={sign} disabled={signing || !agreed || !typedName.trim()}>
            {signing ? 'Signing…' : 'Sign acknowledgement'}
          </Button>
          <p className="text-[11px] text-zinc-600">
            Your name, the date, and your IP address are recorded with this acknowledgement.
          </p>
        </Card>
      )}
    </div>
  )
}
