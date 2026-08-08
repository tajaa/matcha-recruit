import { useEffect, useRef, useState } from 'react'
import { GOOGLE_CLIENT_ID, loadGoogleIdentityScript } from '../api/google'
import { Spinner } from './ui'

export function GoogleSignInButton({
  onCredential,
  disabled,
}: {
  onCredential: (idToken: string) => void
  disabled?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    loadGoogleIdentityScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.google) return
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (response) => onCredential(response.credential),
        })
        window.google.accounts.id.renderButton(containerRef.current, {
          theme: 'filled_black',
          size: 'large',
          text: 'signin_with',
          shape: 'rectangular',
          width: '336',
        })
        setStatus('ready')
      })
      .catch(() => {
        // A blocked script (ad blocker, offline CDN) must not break password
        // login — degrade to nothing rendered rather than an error banner.
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (status === 'error') return null

  return (
    <div className={disabled ? 'pointer-events-none opacity-50' : ''}>
      {status === 'loading' && (
        <div className="flex h-10 items-center justify-center">
          <Spinner />
        </div>
      )}
      <div ref={containerRef} />
    </div>
  )
}
