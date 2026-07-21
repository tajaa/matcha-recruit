import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, CheckCircle2, XCircle, AlertTriangle, ExternalLink } from 'lucide-react'
import { SignatureAttestation } from '../../components/shared/SignatureAttestation'
import { PublicPageShell } from './PublicPageShell'
import { usePublicToken } from './usePublicToken'
import { useState } from 'react'

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
  const { stage, data, error, submit } = usePublicToken<SignatureData>('signatures', 'pending')
  const [typedName, setTypedName] = useState('')
  const [agreed, setAgreed] = useState(false)

  function onSign() {
    if (!typedName.trim() || !agreed) return
    submit('sign', { action: 'sign', signature_data: typedName.trim() })
  }
  function onDecline() {
    submit('decline', { action: 'decline', signature_data: null })
  }

  if (stage === 'validating') {
    return (
      <PublicPageShell>
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin mx-auto" />
      </PublicPageShell>
    )
  }

  if (stage === 'invalid') {
    return (
      <PublicPageShell>
        <XCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Invalid link</h1>
        <p className="text-sm text-zinc-400">
          This signature link is not valid. Contact the sender for a new one.
        </p>
      </PublicPageShell>
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
      <PublicPageShell>
        <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Link unavailable</h1>
        <p className="text-sm text-zinc-400">{msg}</p>
      </PublicPageShell>
    )
  }

  if (stage === 'submitted') {
    return (
      <PublicPageShell>
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Signature recorded</h1>
        <p className="text-sm text-zinc-400">
          Thank you. Your signature has been recorded{data?.company_name ? ` for ${data.company_name}` : ''}.
        </p>
      </PublicPageShell>
    )
  }

  if (stage === 'declined') {
    return (
      <PublicPageShell>
        <XCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-zinc-100 mb-2">Declined</h1>
        <p className="text-sm text-zinc-400">
          You have declined this document. Your response has been recorded.
        </p>
      </PublicPageShell>
    )
  }

  // form | submitting | error
  const content = (data?.policy_content ?? '').trim()
  const canSign = typedName.trim().length > 0 && agreed && stage !== 'submitting'

  return (
    <PublicPageShell wide>
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
        <SignatureAttestation
          agreed={agreed}
          onAgreedChange={setAgreed}
          typedName={typedName}
          onTypedNameChange={setTypedName}
          namePlaceholder={data?.signer_name ?? 'First and last name'}
          variant="raw"
        >
          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={onSign}
              disabled={!canSign}
              className="flex-1 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors flex items-center justify-center"
            >
              {stage === 'submitting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Sign & Accept'}
            </button>
            <button
              type="button"
              onClick={onDecline}
              disabled={stage === 'submitting'}
              className="px-4 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-300 font-medium py-2.5 rounded transition-colors"
            >
              Decline
            </button>
          </div>
        </SignatureAttestation>
      </div>
    </PublicPageShell>
  )
}
