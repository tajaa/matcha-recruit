import { Link } from 'react-router-dom'
import { BOARD, INK, PAPER, STAMP } from '../../components/marketing/kit/theme'
import type { LandingTab } from './scheduling/styles'

/** Shared route navigation; a second row keeps every destination visible on phones. */
export function ProductNav({ tab, dark = false }: { tab: LandingTab; dark?: boolean }) {
  return (
    <nav aria-label="Product" className="order-last flex h-12 w-full shrink-0 items-center justify-center gap-1 md:order-none md:h-auto md:w-auto">
      {[
        { id: 'home', to: '/', label: 'Overview' },
        { id: 'scheduling', to: '/scheduling', label: 'Scheduling' },
        { id: 'incidents', to: '/incidents', label: 'Incident Reporting' },
      ].map(({ id, to, label }) => (
        <Link key={id} to={to} aria-current={tab === id ? 'page' : undefined}
          className="sched-focus relative flex min-h-10 items-center whitespace-nowrap rounded px-2 py-2 text-[12px] font-medium transition-colors md:text-[13px]"
          style={{ color: tab === id ? (dark ? PAPER : INK) : 'inherit', opacity: tab === id ? 1 : 0.7 }}>
          {label}
          {tab === id && <span aria-hidden className="absolute bottom-0 left-2 right-2 h-px" style={{ backgroundColor: dark ? BOARD.STAMP : STAMP }} />}
        </Link>
      ))}
    </nav>
  )
}
