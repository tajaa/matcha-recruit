import { useState } from 'react'
import { useAsync } from '../../../hooks/useAsync'
import { Building2, Plus, Loader2, AlertCircle, Upload } from 'lucide-react'
import { SovImportModal } from '../../../components/property/SovImportModal'
import { fetchPropertySov, deleteBuilding } from '../../../api/property/property'
import type { PropertyBuilding } from '../../../types/property'
import { RiskScoreCard, RollupCards, ExposureCard, ReadinessCard, PlanCard } from './sections'
import { BuildingsTable } from './BuildingsTable'
import { BuildingModal } from './BuildingModal'

export default function Property() {
  const { data, loading, error, reload: load, setData } = useAsync(() => fetchPropertySov(), [], null)
  const [editing, setEditing] = useState<PropertyBuilding | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  function openAdd() { setEditing(null); setShowForm(true) }
  function openEdit(b: PropertyBuilding) { setEditing(b); setShowForm(true) }
  function toggleExpand(id: string) {
    setExpanded((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n })
  }

  async function onDelete(b: PropertyBuilding) {
    if (!confirm(`Remove ${b.name || 'this building'} from the Statement of Values?`)) return
    setData(await deleteBuilding(b.id))
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
      <AlertCircle className="h-8 w-8 mb-2" /><p className="text-sm">Unable to load property.</p>
    </div>
  )

  const { rollup: r, buildings, readiness, exposure, plan, risk } = data

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <Building2 className="h-5 w-5 text-zinc-400" /> Commercial Property
          </h1>
          <p className="text-sm text-zinc-500 mt-1">Your Statement of Values — buildings, COPE, and insurance-to-value. Catastrophe exposure populates once buildings are geocoded.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowImport(true)} className="inline-flex items-center gap-1.5 text-sm text-zinc-300 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Upload className="h-4 w-4" /> Import
          </button>
          <button onClick={openAdd} className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors">
            <Plus className="h-4 w-4" /> Add building
          </button>
        </div>
      </div>

      {risk && risk.score != null && <RiskScoreCard risk={risk} />}

      <RollupCards rollup={r} />

      {exposure && buildings.length > 0 && <ExposureCard exposure={exposure} />}

      {readiness && buildings.length > 0 && <ReadinessCard readiness={readiness} />}

      {plan && plan.fixes.length > 0 && <PlanCard plan={plan} />}

      <BuildingsTable
        buildings={buildings}
        risk={risk}
        exposure={exposure}
        expanded={expanded}
        onToggle={toggleExpand}
        onEdit={openEdit}
        onDelete={onDelete}
      />

      {showForm && (
        <BuildingModal building={editing} onClose={() => setShowForm(false)} onSaved={(sov) => { setData(sov); setShowForm(false) }} />
      )}
      {showImport && (
        <SovImportModal onClose={() => setShowImport(false)} onImported={load} />
      )}
    </div>
  )
}
