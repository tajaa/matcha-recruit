import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { tellusPublicPost } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Card, Spinner } from '../components/ui'
import type { TokenResponse } from '../api/types'
import { AuthShell } from './AuthShell'

export default function Verify() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const { setSession } = useAccount()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true
    if (!token) { setError('Missing confirmation token.'); return }
    tellusPublicPost<TokenResponse>('/auth/verify', { token })
      .then((res) => { setSession(res); navigate('/') })
      .catch((e) => setError(e instanceof Error ? e.message : 'Verification failed'))
  }, [token, setSession, navigate])

  return (
    <AuthShell title="Confirming your email">
      {error ? (
        <>
          <Card><p className="text-sm text-tu-bad">{error}</p></Card>
          <p className="mt-4 text-center text-sm text-tu-dim">
            <Link to="/login" className="font-semibold text-tu-accent hover:underline">Back to sign in</Link>
          </p>
        </>
      ) : (
        <Card><Spinner /></Card>
      )}
    </AuthShell>
  )
}
