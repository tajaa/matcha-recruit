import { Link } from 'react-router-dom'
import { BILLING_PATH } from '../pages/CappeBilling/paths'

/** A plan limit, with the way past it. The server's sentence used to be shown
 *  alone: "Upgrade to create more" and nowhere to do it. */
export default function UpgradeNotice({ message }: { message: string }) {
  return (
    <p role="alert" className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] px-4 py-3 text-sm text-amber-300">
      <span>{message}</span>
      <Link to={BILLING_PATH} className="font-semibold text-amber-200 underline underline-offset-2 hover:text-amber-100">
        See plans
      </Link>
    </p>
  )
}
