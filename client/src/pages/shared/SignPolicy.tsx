import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, CheckCircle2, XCircle, AlertTriangle, ExternalLink } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const inputCls =
  'mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700'

type Stage = 'validating' | 'invalid' | 'used' | 'form' | 'submitting' | 'submitted' | 'declined' | 'error'

// Backend: GET/POST /api/signatures/verify/{token} (public, no auth) —
// server/app/core/routes/public_signatures.py:SignatureDataResponse.
type SignatureData = {
  id: string
  policy_id: string
  policy_title: string | null
  policy_content: string | null
  policy_file_url: string | null
  policy_version: string
  company_name: string | null
  signer_name: string
  signer_email: string
  status: string // pending | signed | declined | expired
  expires_at: string
}

// Public, unauthenticated policy/handbook signature page reached via an emailed
// link (/sign/:token). The token is an opaque lookup key — identity is already
// bound to the row server-side (signer_name/email), so no login is required and
// none should be. The typed legal name is the signature (signature_data).
export default function SignPolicy() {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [data, setData] = useState<SignatureData | null>(null)
  const [typedName, setTypedName] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setStage('invalid')
      return
    }
    fetch(`${BASE}/signatures/verify/${token}`)
      .then(async (res) => {
        if (res.ok) {
          const d = (await res.json().catch(() => null)) as SignatureData | null
          if (!d) {
            setStage('invalid')
            return
          }
          setData(d)
          // A link whose request was already resolved (signed/declined/expired)
          // is a dead end — don't render the form.
          setStage(d.status === 'pending' ? 'form' : 'used')
          return
        }
        if (res.status === 410) setStage('used')
        else setStage('invalid')
      })
      .catch(() => setStage('invalid'))
  }, [token])

  async function submit(action: 'sign' | 'decline') {
    if (action === 'sign' && (!typedName.trim() || !agreed)) return
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${BASE}/signatures/verify/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          signature_data: action === 'sign' ? typedName.trim() : null,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        if (res.status === 410) {
          setStage('used')
          return
        }
        setError(body.detail ?? 'Something went wrong. Please try again.')
        setStage('error')
        return
      }
      setStage(action === 'sign' ? 'submitted' : 'declined')
    } catch {
      setError('Network error. Please try again.')
      setStage('error')
    }
  }

  if (stage === 'validating') {
    return (
      <Shell>
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin mx-auto" />
      </Shell>
    )
  }

  if (stage === 'invalid') {
    return (
      <Shell>
        <XCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Invalid link</h1>
        <p className="text-sm text-zinc-400">
          This signature link is not valid. Contact the sender for a new one.
        </p>
      </Shell>
    )
  }

  if (stage === 'used') {
    const status = data?.status
    const msg =
      status === 'signed'
        ? 'You have already signed this document. No further action is needed.'
        : status === 'declined'
          ? 'You previously declined this document.'
          : status === 'expired'
            ? 'This signature link has expired. Contact the sender for a new one.'
            : 'This signature link is no longer active. Contact the sender for a new one.'
    return (
      <Shell>
        <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Link unavailable</h1>
        <p className="text-sm text-zinc-400">{msg}</p>
      </Shell>
    )
  }

  if (stage === 'submitted') {
    return (
      <Shell>
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Signature recorded</h1>
        <p className="text-sm text-zinc-400">
          Thank you. Your signature has been recorded{data?.company_name ? ` for ${data.company_name}` : ''}.
        </p>
      </Shell>
    )
  }

  if (stage === 'declined') {
    return (
      <Shell>
        <XCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Declined</h1>
        <p className="text-sm text-zinc-400">
          You have declined this document. Your response has been recorded.
        </p>
      </Shell>
    )
  }

  // form | submitting | error
  const content = (data?.policy_content ?? '').trim()
  const canSign = typedName.trim().length > 0 && agreed && stage !== 'submitting'

  return (
    <Shell wide>
      <h1 className="text-lg font-semibold text-zinc-100 mb-1 text-center">
        {data?.policy_title ?? 'Policy signature'}
      </h1>
      <p className="text-sm text-zinc-400 mb-1 text-center">
        {data?.company_name ? `${data.company_name} · ` : ''}Version {data?.policy_version}
      </p>
      <p className="text-xs text-zinc-500 mb-5 text-center">
        Signing as {data?.signer_name} ({data?.signer_email})
      </p>

      {content ? (
        <div className="max-h-[50vh] overflow-y-auto rounded border border-zinc-800 bg-zinc-900/50 p-4 mb-5 text-left">
          <div className="prose prose-sm prose-invert prose-zinc max-w-none text-sm leading-relaxed text-zinc-300 prose-headings:text-zinc-100 prose-p:my-2">
            <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
          </div>
        </div>
      ) : data?.policy_file_url ? (
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4 mb-5 text-left">
          <a
            href={data.policy_file_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-emerald-400 hover:text-emerald-300"
          >
            <ExternalLink className="w-4 h-4" /> View policy document
          </a>
          <p className="mt-2 text-xs text-zinc-500">
            Please review the document above before signing.
          </p>
        </div>
      ) : (
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4 mb-5 text-sm text-zinc-500 text-left">
          The policy content is unavailable. Contact the sender for a copy before signing.
        </div>
      )}

      <div className="space-y-4 text-left">
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

        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">
            Type your full legal name to sign
          </span>
          <input
            type="text"
            value={typedName}
            onChange={(e) => setTypedName(e.target.value)}
            maxLength={255}
            autoComplete="name"
            placeholder={data?.signer_name ?? 'First and last name'}
            className={inputCls}
          />
        </label>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => submit('sign')}
            disabled={!canSign}
            className="flex-1 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center"
          >
            {stage === 'submitting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Sign & Accept'}
          </button>
          <button
            type="button"
            onClick={() => submit('decline')}
            disabled={stage === 'submitting'}
            className="px-4 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-300 font-medium py-2.5 rounded transition-colors"
          >
            Decline
          </button>
        </div>

        <p className="text-[11px] text-zinc-600">
          Your name, the date, and your IP address are recorded with this signature.
        </p>
      </div>
    </Shell>
  )
}

function Shell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-10">
      <div className={`${wide ? 'max-w-xl' : 'max-w-md'} w-full text-center`}>{children}</div>
    </div>
  )
}
