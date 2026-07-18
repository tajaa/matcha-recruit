import { Building2, Send, MapPin } from 'lucide-react'
import { Button } from '../../../components/ui'
import { LABEL } from '../../../components/ui/typography'
import type { ClientSetup } from './types'
import { statusBadge, onboardingStageBadge, locationSummary } from './badges'

type Props = {
  setups: ClientSetup[]
  sendingInvite: string | null
  onSendInvite: (setupId: string) => void
  onAddClient: () => void
}

export function ClientSetupsTable({ setups, sendingInvite, onSendInvite, onAddClient }: Props) {
  if (setups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-zinc-500 rounded-xl border border-white/[0.08] border-dashed bg-zinc-950">
        <Building2 className="h-10 w-10 mb-3 text-zinc-600" />
        <p className="text-sm font-medium text-zinc-400">No client setups yet</p>
        <p className="text-xs mt-1">Create a client setup to start onboarding a company.</p>
        <Button size="sm" className="mt-4" onClick={onAddClient}>
          Add Your First Client
        </Button>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <table className="w-full text-sm text-left">
        <thead>
          <tr className="border-b border-white/[0.06]">
            <th className={`px-4 py-3 ${LABEL}`}>Company</th>
            <th className={`px-4 py-3 ${LABEL}`}>Contact</th>
            <th className={`px-4 py-3 ${LABEL}`}>Status</th>
            <th className={`px-4 py-3 ${LABEL}`}>Onboarding</th>
            <th className={`px-4 py-3 ${LABEL}`}>Created</th>
            <th className={`px-4 py-3 text-right ${LABEL}`}>Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.06]">
          {setups.map((s) => {
            const locText = locationSummary(s.locations)
            return (
              <tr key={s.id} className="text-zinc-300">
                <td className="px-4 py-3">
                  <p className="font-medium text-zinc-100">{s.company_name}</p>
                  {locText && (
                    <p className="text-xs text-zinc-500 flex items-center gap-1 mt-0.5">
                      <MapPin size={10} />
                      {locText}
                    </p>
                  )}
                </td>
                <td className="px-4 py-3">
                  <p className="text-zinc-300">{s.contact_name || '—'}</p>
                  <p className="text-xs text-zinc-500">{s.contact_email || ''}</p>
                </td>
                <td className="px-4 py-3">{statusBadge(s.status)}</td>
                <td className="px-4 py-3">{onboardingStageBadge(s.onboarding_stage)}</td>
                <td className="px-4 py-3 text-xs text-zinc-500">
                  {new Date(s.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 text-right">
                  {(s.status === 'draft' || s.status === 'expired') && s.contact_email && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={sendingInvite === s.id}
                      onClick={() => onSendInvite(s.id)}
                    >
                      <Send size={12} className="mr-1" />
                      {sendingInvite === s.id ? 'Sending...' : 'Send Invite'}
                    </Button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
