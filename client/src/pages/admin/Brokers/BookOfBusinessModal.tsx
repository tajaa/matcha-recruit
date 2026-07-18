import { Badge, Modal } from '../../../components/ui'
import type { Broker } from './types'

type BookOfBusinessModalProps = {
  bookBroker: Broker | null
  bookSetups: any[]
  bookLoading: boolean
  onClose: () => void
}

export function BookOfBusinessModal({ bookBroker, bookSetups, bookLoading, onClose }: BookOfBusinessModalProps) {
  return (
    <Modal open={!!bookBroker} onClose={onClose} title={`${bookBroker?.name ?? ''} — Book of Business`} width="lg">
      {bookLoading ? (
        <p className="text-sm text-zinc-500 py-4">Loading...</p>
      ) : bookSetups.length === 0 ? (
        <p className="text-sm text-zinc-500 py-4">No client setups submitted by this broker.</p>
      ) : (
        <div className="space-y-3 max-h-[60vh] overflow-y-auto">
          {bookSetups.map((s: any) => (
            <div key={s.id} className="border border-zinc-800 rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-zinc-100">{s.company_name}</p>
                  <p className="text-xs text-zinc-500">
                    {s.industry ?? '—'} · {s.company_size ?? '—'} · {s.headcount ? `${s.headcount} employees` : '—'}
                  </p>
                </div>
                <Badge variant={s.status === 'activated' ? 'success' : s.status === 'invited' ? 'warning' : 'neutral'}>
                  {s.status}
                </Badge>
              </div>
              {s.contact_name && (
                <p className="text-xs text-zinc-400">Contact: {s.contact_name} {s.contact_email ? `· ${s.contact_email}` : ''} {s.contact_phone ? `· ${s.contact_phone}` : ''}</p>
              )}
              {s.locations && s.locations.length > 0 && (
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Locations / Jurisdictions</p>
                  <div className="flex flex-wrap gap-1">
                    {s.locations.map((loc: any, i: number) => (
                      <span key={i} className="text-[11px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded">
                        {loc.city}{loc.state ? `, ${loc.state}` : ''} {loc.type ? `(${loc.type})` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {s.specialties && (
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Specialties</p>
                  <p className="text-xs text-zinc-300">{s.specialties}</p>
                </div>
              )}
              {s.notes && (
                <div>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Notes</p>
                  <p className="text-xs text-zinc-400">{s.notes}</p>
                </div>
              )}
              <p className="text-[10px] text-zinc-600">Submitted {new Date(s.created_at).toLocaleDateString()}</p>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
