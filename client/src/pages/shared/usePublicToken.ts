import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// Shared state machine for the public, token-gated signing pages (SignPolicy,
// SignEmployeeDocument). The token is an opaque lookup key bound server-side to
// the row's identity, so these endpoints are unauthenticated and use bare
// fetch() rather than the auth-attaching api/client helper.
export type Stage =
  | 'validating'
  | 'invalid'
  | 'used'
  | 'form'
  | 'submitting'
  | 'submitted'
  | 'declined'
  | 'error'

// `basePath` is the endpoint segment: 'signatures' → /api/signatures/verify/{token},
// 'employee-documents' → /api/employee-documents/verify/{token}.
// `pendingStatus` is the row status that means "still needs a signature"
// ('pending' for policies, 'pending_signature' for employee documents).
export function usePublicToken<T extends { status: string }>(
  basePath: string,
  pendingStatus: string,
) {
  const { token } = useParams<{ token: string }>()
  const [stage, setStage] = useState<Stage>('validating')
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setStage('invalid')
      return
    }
    fetch(`${BASE}/${basePath}/verify/${token}`)
      .then(async (res) => {
        if (res.ok) {
          const d = (await res.json().catch(() => null)) as T | null
          if (!d) {
            setStage('invalid')
            return
          }
          setData(d)
          // A link whose request was already resolved (signed/declined/expired)
          // is a dead end — don't render the form.
          setStage(d.status === pendingStatus ? 'form' : 'used')
          return
        }
        if (res.status === 410) setStage('used')
        else setStage('invalid')
      })
      .catch(() => setStage('invalid'))
  }, [token])

  // `body` is the exact JSON body to POST (kept caller-shaped so each page keeps
  // its own request contract verbatim). `action` only decides the success stage:
  // 'decline' → 'declined', anything else → 'submitted'.
  async function submit(action: 'sign' | 'decline', body: unknown) {
    setStage('submitting')
    setError(null)
    try {
      const res = await fetch(`${BASE}/${basePath}/verify/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string }
        if (res.status === 410) {
          setStage('used')
          return
        }
        setError(errBody.detail ?? 'Something went wrong. Please try again.')
        setStage('error')
        return
      }
      setStage(action === 'sign' ? 'submitted' : 'declined')
    } catch {
      setError('Network error. Please try again.')
      setStage('error')
    }
  }

  return { token, stage, setStage, data, error, setError, submit }
}
