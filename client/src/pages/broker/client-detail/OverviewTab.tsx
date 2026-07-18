import { MapPin, FileText, AlertTriangle, Building2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import type { BrokerClientDetailResponse } from '../../../types/broker'
import { complianceColor } from './shared'

export function OverviewTab({
  compliance,
  policies,
  ir,
  er,
  onboardingStage,
}: {
  compliance: BrokerClientDetailResponse['compliance']
  policies: BrokerClientDetailResponse['policies']
  ir: BrokerClientDetailResponse['ir_summary']
  er: BrokerClientDetailResponse['er_summary']
  onboardingStage: string | null
}) {
  return (
    <div className="space-y-4">
      {onboardingStage && (
        <Card className="p-4">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Onboarding Stage</h3>
          <p className="text-sm text-zinc-200 capitalize">{onboardingStage.replace(/_/g, ' ')}</p>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <MapPin className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Compliance Locations</h3>
          </div>
          <p className="text-xl font-semibold text-zinc-100">{compliance.total_locations}</p>
          <p className="text-xs text-zinc-500 mt-1">{compliance.total_requirements} total requirements</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Policy Compliance</h3>
          </div>
          <p className={`text-xl font-semibold ${complianceColor(policies.compliance_rate)}`}>
            {Math.round(policies.compliance_rate)}%
          </p>
          <p className="text-xs text-zinc-500 mt-1">{policies.total_active} active policies</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Open Incidents</h3>
          </div>
          <p className="text-xl font-semibold text-zinc-100">{ir.total_open}</p>
          <p className="text-xs text-zinc-500 mt-1">{ir.recent_30_days} in last 30 days</p>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Building2 className="h-4 w-4 text-zinc-500" />
            <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">ER Cases</h3>
          </div>
          <p className="text-xl font-semibold text-zinc-100">{er.total_open}</p>
          <p className="text-xs text-zinc-500 mt-1">open cases</p>
        </Card>
      </div>
    </div>
  )
}
