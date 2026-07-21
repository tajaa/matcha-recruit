import type { ReactNode } from 'react'
import { Input } from '../ui'

// Shared attestation block for signature/acknowledgement flows: the agree
// checkbox, the "type your full legal name to sign" input, and the small-print
// footer recording name/date/IP. Two visual variants:
//   - 'raw'  — the public token-signing pages' bare inputs (SignPolicy,
//              SignEmployeeDocument), styled with inputCls.
//   - 'kit'  — the ui-kit <Input> + raw checkbox as the authenticated portal
//              page (EmployeeSignDocument) renders it.
// The Sign/Decline buttons are NOT part of this component — each page keeps its
// own, passed as `children` so they stay interleaved between the name input and
// the footer (their current DOM position).

const inputCls =
  'mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700'

const DEFAULT_FOOTER =
  'Your name, the date, and your IP address are recorded with this signature.'

type SignatureAttestationProps = {
  agreed: boolean
  onAgreedChange: (v: boolean) => void
  typedName: string
  onTypedNameChange: (v: string) => void
  namePlaceholder?: string
  footerText?: string
  variant?: 'raw' | 'kit'
  children?: ReactNode
}

export function SignatureAttestation({
  agreed,
  onAgreedChange,
  typedName,
  onTypedNameChange,
  namePlaceholder = 'First and last name',
  footerText = DEFAULT_FOOTER,
  variant = 'raw',
  children,
}: SignatureAttestationProps) {
  return (
    <>
      <label className="flex items-start gap-2 text-xs text-zinc-400">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => onAgreedChange(e.target.checked)}
          className="mt-0.5 accent-emerald-500"
        />
        <span>
          I confirm I have received, read, and understand this document, and agree to comply
          with it.
        </span>
      </label>

      {variant === 'kit' ? (
        <Input
          label="Type your full legal name to sign"
          value={typedName}
          onChange={(e) => onTypedNameChange(e.target.value)}
          placeholder={namePlaceholder}
        />
      ) : (
        <label className="block">
          <span className="text-xs text-zinc-400 uppercase tracking-wide">
            Type your full legal name to sign
          </span>
          <input
            type="text"
            value={typedName}
            onChange={(e) => onTypedNameChange(e.target.value)}
            maxLength={255}
            autoComplete="name"
            placeholder={namePlaceholder}
            className={inputCls}
          />
        </label>
      )}

      {children}

      <p className="text-[11px] text-zinc-600">{footerText}</p>
    </>
  )
}
