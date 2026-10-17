import { AdminButton as Button, AdminButton } from '../../../../../components/admin/AdminUI'
import { useState } from 'react'
import { Building2, X } from 'lucide-react'

import { LABEL } from '../../../../../components/ui/typography'
import { CompanyPicker } from '../../../sales/gap-analysis/AdminOnboarding'
import StatutoryFitPanel from '../../../../../components/admin/onboarding/StatutoryFitPanel'
import type { FitGatedRow } from '../../../../../api/admin/adminOnboarding'

// ── §0 Company focus ──
// The per-company job on the same funnel: pick a tenant, see what it
// still needs, and finish every step here — research, approve, codify —
// instead of the work being spread across Compliance Mgmt, Gap Analysis
// and this tab with no thread between them.
export function CompanyFocus({
  companyId, onCompanyChange, fitRefresh, onCodifyGated,
}: {
  companyId?: string | null
  onCompanyChange?: (id: string | null) => void
  fitRefresh: number
  onCodifyGated: (rows: FitGatedRow[]) => void
}) {
  const [pickerOpen, setPickerOpen] = useState(false)

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <h2 className={LABEL}>{companyId ? 'Filling gaps for one company' : 'Fleet queue'}</h2>
        {companyId ? (
          <AdminButton type="button" onClick={() => onCompanyChange?.(null)}
                  className="gap-1.5 h-8" variant="success">
            <Building2 className="h-3.5 w-3.5" /> Focused — clear <X className="h-3 w-3" />
          </AdminButton>
        ) : (
          <Button variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>
            <Building2 className="h-3.5 w-3.5" /> Focus a company
          </Button>
        )}
      </div>
      {pickerOpen && (
        <CompanyPicker onClose={() => setPickerOpen(false)}
                       onPick={(id) => { setPickerOpen(false); onCompanyChange?.(id) }} />
      )}
      {companyId && (
        <StatutoryFitPanel companyId={companyId} onCodifyGated={onCodifyGated} refreshKey={fitRefresh} />
      )}
    </>
  )
}
