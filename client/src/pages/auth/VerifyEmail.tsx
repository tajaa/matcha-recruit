import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, MailCheck, AlertCircle } from 'lucide-react'
import { invalidateMeCache } from '../../hooks/useMe'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type State = 'verifying' | 'success' | 'error'

/**
 * Resources_free signup verification landing.
 * Backend signed signup data into a JWT; this page exchanges it for an
 * account + auth tokens, then drops the user into /app/resources.
 */
export default function VerifyEmail() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token')

  const [state, setState] = useState<State>('verifying')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  // StrictMode mounts effects twice in dev — guard the network call.
  const ranRef = useRef(false)

  useEffect(() => {
    if (ranRef.current) return
    ranRef.current = true

    if (!token) {
      setState('error')
      setErrorMsg('Missing verification token. Use the link from your email.')
      return
    }

    ;(async () => {
      try {
        const res = await fetch(`${BASE}/auth/verify-email`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        })
        const data = await res.json()
        if (!res.ok) {
          setState('error')
          setErrorMsg(data.detail ?? 'Verification failed')
          return
        }
        localStorage.setItem('matcha_access_token', data.access_token)
        localStorage.setItem('matcha_refresh_token', data.refresh_token)
        invalidateMeCache()
        setState('success')
        setTimeout(() => navigate(data.next ?? '/app/resources'), 800)
      } catch {
        setState('error')
        setErrorMsg('Something went wrong. Please try again.')
      }
    })()
  }, [token, navigate])

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-12"
      style={{ backgroundColor: BG, color: INK }}
    >
      <div className="w-full max-w-md">
        <Link to="/" className="block text-center mb-10">
          <span
            className="text-3xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Matcha
          </span>
        </Link>
        <div
          className="rounded-2xl p-8 text-center"
          style={{ backgroundColor: 'rgba(255,255,255,0.5)', border: `1px solid ${LINE}` }}
        >
          {state === 'verifying' && (
            <>
              <Loader2 className="w-10 h-10 mx-auto mb-4 animate-spin" style={{ color: INK }} />
              <h1
                className="tracking-tight mb-2"
                style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.5rem', color: INK }}
              >
                Confirming your email…
              </h1>
            </>
          )}
          {state === 'success' && (
            <>
              <MailCheck className="w-10 h-10 mx-auto mb-4" style={{ color: INK }} />
              <h1
                className="tracking-tight mb-2"
                style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.5rem', color: INK }}
              >
                You're in.
              </h1>
              <p className="text-sm" style={{ color: MUTED }}>Redirecting to your resources…</p>
            </>
          )}
          {state === 'error' && (
            <>
              <AlertCircle className="w-10 h-10 mx-auto mb-4" style={{ color: '#8a4a3a' }} />
              <h1
                className="tracking-tight mb-2"
                style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.5rem', color: INK }}
              >
                Verification failed
              </h1>
              <p className="text-sm mb-4" style={{ color: MUTED }}>
                {errorMsg ?? 'The link is invalid or expired.'}
              </p>
              <Link
                to="/auth/resources-signup"
                className="inline-block px-5 h-10 leading-10 rounded-full text-sm font-medium"
                style={{ backgroundColor: INK, color: BG }}
              >
                Start over
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
