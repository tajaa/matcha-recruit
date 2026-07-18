import { Button, Modal } from '../../../components/ui'
import type { Broker, CompanyOption } from './types'

type LinkCompanyModalProps = {
  linkBroker: Broker | null
  companies: CompanyOption[]
  companiesLoading: boolean
  selectedCompanyId: string
  setSelectedCompanyId: (id: string) => void
  linkSaving: boolean
  linkError: string
  linkSuccess: string
  onClose: () => void
  onLink: () => void
}

export function LinkCompanyModal({
  linkBroker,
  companies,
  companiesLoading,
  selectedCompanyId,
  setSelectedCompanyId,
  linkSaving,
  linkError,
  linkSuccess,
  onClose,
  onLink,
}: LinkCompanyModalProps) {
  return (
    <Modal open={!!linkBroker} onClose={onClose} title={`Link Company to ${linkBroker?.name ?? ''}`} width="md">
      <div className="space-y-4">
        {companiesLoading ? (
          <p className="text-sm text-zinc-500">Loading companies...</p>
        ) : (
          <>
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Select Company</label>
              <select
                value={selectedCompanyId}
                onChange={(e) => setSelectedCompanyId(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="">Choose a company...</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} — {c.status}{c.industry ? ` (${c.industry})` : ''}
                  </option>
                ))}
              </select>
            </div>

            {linkError && <p className="text-sm text-red-400">{linkError}</p>}
            {linkSuccess && (
              <div className="text-sm text-emerald-400 bg-emerald-900/20 border border-emerald-800/30 rounded px-3 py-2">
                {linkSuccess}
              </div>
            )}

            <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
              <Button size="sm" onClick={onLink} disabled={linkSaving || !selectedCompanyId}>
                {linkSaving ? 'Linking...' : 'Link Company'}
              </Button>
              <Button size="sm" variant="ghost" onClick={onClose}>
                {linkSuccess ? 'Done' : 'Cancel'}
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
