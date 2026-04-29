import { Navigate, useLocation } from 'react-router-dom'
import { useMe } from '../../hooks/useMe'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

interface Props {
  children: React.ReactNode
}

export default function RequireBusinessAccount({ children }: Props) {
  const { me, loading } = useMe()
  const location = useLocation()

  if (loading) {
    return (
      <div
        style={{ backgroundColor: BG, color: MUTED, minHeight: '100vh' }}
        className="flex items-center justify-center text-sm"
      >
        Loading…
      </div>
    )
  }

  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/auth/resources-signup?next=${next}`} replace />
  }

  if (me.user.role !== 'client') {
    return (
      <div
        style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}
        className="flex items-center justify-center px-6"
      >
        <div
          className="max-w-md w-full p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}` }}
        >
          <h1
            className="text-2xl mb-3"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Switch to a business account
          </h1>
          <p className="text-sm mb-6" style={{ color: MUTED }}>
            HR resources are reserved for business accounts. You're signed in
            as <strong style={{ color: INK }}>{me.user.role}</strong>.
            Sign in with a business account or create one to access templates,
            calculators, and the compliance audit.
          </p>
          <a
            href="/auth/resources-signup"
            className="inline-block px-5 h-10 rounded-full text-sm font-medium leading-10"
            style={{ backgroundColor: INK, color: BG }}
          >
            Create business account
          </a>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
