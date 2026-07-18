import { Button } from '../../../components/ui'
import { Link2 } from 'lucide-react'
import type { Broker } from './types'
import { statusBadge } from './helpers'

type BrokerTableProps = {
  loading: boolean
  filtered: Broker[]
  onViewBook: (b: Broker) => void
  onLinkCompany: (b: Broker) => void
  onEdit: (b: Broker) => void
}

export function BrokerTable({ loading, filtered, onViewBook, onLinkCompany, onEdit }: BrokerTableProps) {
  if (loading) {
    return <p className="text-sm text-zinc-500">Loading...</p>
  }
  if (filtered.length === 0) {
    return <p className="text-sm text-zinc-500">No brokers found.</p>
  }
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      <table className="w-full text-sm text-left">
        <thead className="bg-zinc-900/50 text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Broker</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Members</th>
            <th className="px-4 py-3 font-medium">Companies</th>
            <th className="px-4 py-3 font-medium">Seats</th>
            <th className="px-4 py-3 font-medium">Billing</th>
            <th className="px-4 py-3 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {filtered.map((b) => (
            <tr key={b.id} className="text-zinc-300">
              <td className="px-4 py-3">
                <p className="font-medium text-zinc-100">{b.name}</p>
                <p className="text-xs text-zinc-500">/{b.slug}</p>
              </td>
              <td className="px-4 py-3">{statusBadge(b.status)}</td>
              <td className="px-4 py-3">{b.active_member_count}</td>
              <td className="px-4 py-3">{b.active_company_count}</td>
              <td className="px-4 py-3">
                <span className="text-xs text-zinc-400 tabular-nums">
                  {b.seats_used ?? 0} / {b.allocated_seats ?? 0}
                </span>
              </td>
              <td className="px-4 py-3">
                <span className="text-xs text-zinc-400 capitalize">{b.billing_mode}</span>
                {b.active_contract?.pepm_rate ? (
                  <span className="ml-1 text-xs text-zinc-500">
                    ${b.active_contract.pepm_rate}/pepm
                  </span>
                ) : null}
              </td>
              <td className="px-4 py-3 text-right space-x-1">
                <Button size="sm" variant="ghost" onClick={() => onViewBook(b)}>
                  Book
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onLinkCompany(b)}>
                  <Link2 size={12} className="mr-1" />
                  Link
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onEdit(b)}>
                  Edit
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
