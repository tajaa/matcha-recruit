import { useState } from 'react'
import { Button } from '../../../components/ui'
import CoverageHeatmap from '../../../components/admin/jurisdiction/CoverageHeatmap'
import RequirementAuditTable from '../../../components/admin/jurisdiction/RequirementAuditTable'
import GapIntelligencePanel from '../../../components/admin/jurisdiction/GapIntelligencePanel'
import KeyCoverageDrawer from '../../../components/admin/jurisdiction/KeyCoverageDrawer'

export default function QualityTab() {
  const [qualityView, setQualityView] = useState<'heatmap' | 'table' | 'gaps'>('heatmap')
  const [keyCoverageDrawer, setKeyCoverageDrawer] = useState<{
    jurisdictionId?: string; category?: string
  } | null>(null)

  return (
    <div className="space-y-4">
      {/* Segmented control */}
      <div className="flex items-center gap-1">
        {([
          { id: 'heatmap' as const, label: 'Heatmap' },
          { id: 'table' as const, label: 'Audit Table' },
          { id: 'gaps' as const, label: 'Gaps' },
        ]).map((v) => (
          <Button
            key={v.id}
            variant={qualityView === v.id ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setQualityView(v.id)}
          >
            {v.label}
          </Button>
        ))}
        <div className="ml-auto">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setKeyCoverageDrawer({})}
          >
            Key Coverage
          </Button>
        </div>
      </div>

      {qualityView === 'heatmap' && (
        <CoverageHeatmap
          onCellClick={(jurisdictionId, category) => {
            setKeyCoverageDrawer({ jurisdictionId, category })
          }}
        />
      )}

      {keyCoverageDrawer && (
        <KeyCoverageDrawer
          jurisdictionId={keyCoverageDrawer.jurisdictionId}
          category={keyCoverageDrawer.category}
          onClose={() => setKeyCoverageDrawer(null)}
        />
      )}

      {qualityView === 'table' && (
        <RequirementAuditTable
          onEditRequirement={(requirementId) => {
            // Open the jurisdiction that owns this requirement in the detail panel
            // For now log — full wiring would require a req→jurisdiction lookup
            console.log('[Quality] Edit requirement:', requirementId)
          }}
        />
      )}

      {qualityView === 'gaps' && <GapIntelligencePanel />}
    </div>
  )
}
