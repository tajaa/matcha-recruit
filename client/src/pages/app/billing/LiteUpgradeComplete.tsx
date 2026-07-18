import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useMe } from '../../../hooks/useMe'

const POLL_MS = 2500
const TIMEOUT_MS = 45000

/** Landing page for the Essentials → Lite upgrade Stripe redirect
 *  (`/app/upgrade/complete`). The redirect can beat the webhook, so poll
 *  /auth/me until signup_source flips (the tier overlay then carries
 *  `employees`), then land on the roster with the welcome banner. A dedicated
 *  page (rather than /app/employees directly) because the Employees route is
 *  feature-gated — arriving before the flip would show the upsell card. */
export default function LiteUpgradeComplete() {
  const navigate = useNavigate()
  const { me, refresh } = useMe()
  const [timedOut, setTimedOut] = useState(false)
  const startedAt = useRef(Date.now())

  const upgraded =
    me?.profile?.signup_source === 'matcha_lite' && !!me?.profile?.enabled_features?.employees

  useEffect(() => {
    if (upgraded) {
      navigate('/app/employees?upgraded=1', { replace: true })
      return
    }
    if (timedOut) return
    const t = setTimeout(() => {
      if (Date.now() - startedAt.current > TIMEOUT_MS) setTimedOut(true)
      else refresh()
    }, POLL_MS)
    return () => clearTimeout(t)
  }, [upgraded, timedOut, me, refresh, navigate])

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      {timedOut ? (
        <>
          <h1 className="text-lg font-semibold text-zinc-100">Payment received</h1>
          <p className="mt-2 max-w-md text-sm text-zinc-500">
            Your upgrade is still activating — this usually takes a few seconds. Refresh in a
            moment, or contact <a href="mailto:hello@matcha.work" className="underline text-zinc-300">support</a> if
            it doesn't come through.
          </p>
        </>
      ) : (
        <>
          <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
          <h1 className="mt-4 text-lg font-semibold text-zinc-100">Activating Matcha Lite…</h1>
          <p className="mt-2 text-sm text-zinc-500">
            Unlocking your employee roster and OSHA logs.
          </p>
        </>
      )}
    </div>
  )
}
