import { Button, DataTable } from '../../../components/ui'
import { Link2 } from 'lucide-react'
import type { Broker } from './types'
import { statusBadge } from './helpers'

type BrokerTableProps = {
  loading: boolean
  error?: string | null
  filtered: Broker[]
  onViewBook: (b: Broker) => void
  onLinkCompany: (b: Broker) => void
  onEdit: (b: Broker) => void
}

export function BrokerTable({ loading, error, filtered, onViewBook, onLinkCompany, onEdit }: BrokerTableProps) {
  return (
    <DataTable
      rows={filtered}
      rowKey={(b) => b.id}
      loading={loading}
      error={error}
      emptyText="No brokers found."
      columns={[
        {
          key: 'broker',
          header: 'Broker',
          render: (b) => (
            <>
              <p className="font-medium text-zinc-100">{b.name}</p>
              <p className="text-xs text-zinc-500">/{b.slug}</p>
            </>
          ),
        },
        { key: 'status', header: 'Status', render: (b) => statusBadge(b.status) },
        { key: 'members', header: 'Members', render: (b) => b.active_member_count },
        { key: 'companies', header: 'Companies', render: (b) => b.active_company_count },
        {
          key: 'seats',
          header: 'Seats',
          render: (b) => (
            <span className="text-xs text-zinc-400 tabular-nums">
              {b.seats_used ?? 0} / {b.allocated_seats ?? 0}
            </span>
          ),
        },
        {
          key: 'billing',
          header: 'Billing',
          render: (b) => (
            <>
              <span className="text-xs text-zinc-400 capitalize">{b.billing_mode}</span>
              {b.active_contract?.pepm_rate ? (
                <span className="ml-1 text-xs text-zinc-500">
                  ${b.active_contract.pepm_rate}/pepm
                </span>
              ) : null}
            </>
          ),
        },
        {
          key: 'actions',
          header: 'Actions',
          align: 'right',
          className: 'space-x-1',
          render: (b) => (
            <>
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
            </>
          ),
        },
      ]}
    />
  )
}
