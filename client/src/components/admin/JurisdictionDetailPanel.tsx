import { AdminButton } from './AdminUI'
import { AdminTab, AdminTabBar } from './AdminTabs'
import SpecialtyFilterSelect from './jurisdiction/SpecialtyFilterSelect'
import type { Props, RowContext, ViewMode } from './JurisdictionDetailPanel/types'
import { getCategoryLabel } from './JurisdictionDetailPanel/helpers'
import { useJurisdictionDetail } from './JurisdictionDetailPanel/useJurisdictionDetail'
import Toolbar from './JurisdictionDetailPanel/Toolbar'
import FederalSourcesPreview from './JurisdictionDetailPanel/FederalSourcesPreview'
import RequirementsView from './JurisdictionDetailPanel/RequirementsView'
import HierarchyView from './JurisdictionDetailPanel/HierarchyView'
import LegislationView from './JurisdictionDetailPanel/LegislationView'

export default function JurisdictionDetailPanel({ id, city, state, categoriesMissing, preemptionRules, selectedProfile, onCheckComplete, onNavigate, initialIndustry, initialReq, onViewCoverage }: Props) {
  const h = useJurisdictionDetail({ id, state, preemptionRules, selectedProfile, onCheckComplete, initialIndustry, initialReq })
  const {
    detail, loading,
    scanning, specialtyRunning, medicalRunning, lifeSciRunning, fedSourcesRunning,
    fedPreview, setFedPreview, fedApplying,
    scanMessages,
    viewMode, setViewMode,
    specialtyFilter, setSpecialtyFilter,
    categoryFilter, setCategoryFilter,
    editingId, setEditingId,
    editForm, setEditForm,
    saving, reordering,
    startCheck, startSpecialtyCheck, startMedicalCheck, startLifeSciCheck, startFedSourcesCheck,
    applyFedSources, toggleBookmark, startEditing, saveEdit, reorderReq,
    filteredReqs, availableCategories, categoryFilteredReqs, sectioned, hierarchyGrouped,
    preemptionLookup, profileFocused, profileEvidence,
  } = h

  const rowCtx: RowContext = {
    editingId, editForm, setEditForm, saving, saveEdit, setEditingId,
    reordering, reorderReq, toggleBookmark, startEditing,
    profileFocused, profileEvidence, initialReq,
  }

  return (
    <div>
      {/* Header */}
      <Toolbar
        city={city} state={state} detail={detail} loading={loading}
        scanning={scanning} specialtyRunning={specialtyRunning} medicalRunning={medicalRunning}
        lifeSciRunning={lifeSciRunning} fedSourcesRunning={fedSourcesRunning}
        onViewCoverage={onViewCoverage}
        startCheck={startCheck} startSpecialtyCheck={startSpecialtyCheck} startMedicalCheck={startMedicalCheck}
        startLifeSciCheck={startLifeSciCheck} startFedSourcesCheck={startFedSourcesCheck}
      />

      {/* Metro group (parent/children) */}
      {detail && (detail.parent_id || detail.children.length > 0) && (
        <div className="mb-3 border border-zinc-800 rounded-lg px-3 py-2.5">
          <p className="text-[11px] text-zinc-500 font-medium mb-1.5">Metro Group</p>
          <div className="flex flex-wrap gap-1.5">
            {detail.parent_id && onNavigate && (
              <AdminButton type="button" onClick={() => onNavigate(detail.parent_id!)}
                className="text-amber-400" variant="ghost">
                Parent ↑
              </AdminButton>
            )}
            {detail.children.map((c) => (
              <AdminButton key={c.id} type="button" onClick={() => onNavigate?.(c.id)}
                className="text-blue-400" variant="ghost">
                {c.city}, {c.state}
              </AdminButton>
            ))}
          </div>
        </div>
      )}

      {/* Missing categories */}
      {categoriesMissing && categoriesMissing.length > 0 && (
        <div className="mb-3 border border-zinc-800 rounded-lg px-3 py-2.5">
          <p className="text-[11px] text-zinc-500 font-medium mb-1.5">Missing categories</p>
          <div className="flex flex-wrap gap-1.5">
            {categoriesMissing.map((cat) => (
              <span key={cat} className="text-[10px] text-red-400/70 bg-red-500/10 px-2 py-0.5 rounded">{getCategoryLabel(cat)}</span>
            ))}
          </div>
        </div>
      )}

      {/* View controls: mode tabs + specialty filter */}
      <div className="flex items-center justify-between mb-3">
        <AdminTabBar className="mb-0!">
          {([
            { id: 'requirements' as ViewMode, label: 'Requirements' },
            { id: 'hierarchy' as ViewMode, label: 'Hierarchy' },
            { id: 'legislation' as ViewMode, label: 'Legislation' },
          ]).map((v) => (
            <AdminTab key={v.id} active={viewMode === v.id} onClick={() => setViewMode(v.id)}>
              {v.label}
            </AdminTab>
          ))}
        </AdminTabBar>
        <SpecialtyFilterSelect value={specialtyFilter} onChange={setSpecialtyFilter} />
      </div>

      {/* SSE scan log */}
      {(scanning || specialtyRunning || medicalRunning || lifeSciRunning || fedSourcesRunning) && scanMessages.length > 0 && (
        <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
          {scanMessages.map((msg, i) => <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>)}
        </div>
      )}

      {/* Federal Sources preview */}
      {fedPreview && (
        <FederalSourcesPreview
          fedPreview={fedPreview} fedApplying={fedApplying}
          setFedPreview={setFedPreview} applyFedSources={applyFedSources}
        />
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : !detail ? (
        <p className="text-sm text-zinc-600">Failed to load detail.</p>
      ) : (
        <>
          {/* ── Category filter strip ── */}
          {filteredReqs.length > 0 && (viewMode === 'requirements' || viewMode === 'hierarchy') && (
            <AdminTabBar className="mb-3!">
              <AdminTab onClick={() => setCategoryFilter(null)} active={!categoryFilter}>
                All ({filteredReqs.length})
              </AdminTab>
              {availableCategories.map(({ cat, count, label }) => (
                <AdminTab
                  key={cat}
                  onClick={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
                 active={categoryFilter === cat}
                >
                  {label} ({count})
                </AdminTab>
              ))}
            </AdminTabBar>
          )}

          {/* ── Requirements view ── */}
          {viewMode === 'requirements' && (
            <RequirementsView
              detail={detail} specialtyFilter={specialtyFilter}
              categoryFilteredReqs={categoryFilteredReqs} sectioned={sectioned}
              onNavigate={onNavigate} ctx={rowCtx}
            />
          )}

          {/* ── Hierarchy view ── */}
          {viewMode === 'hierarchy' && (
            <HierarchyView
              filteredReqs={filteredReqs} hierarchyGrouped={hierarchyGrouped}
              preemptionLookup={preemptionLookup} city={city} state={state} ctx={rowCtx}
            />
          )}

          {/* ── Legislation view ── */}
          {viewMode === 'legislation' && (
            <LegislationView legislation={detail.legislation} />
          )}

          {/* Linked locations */}
          {detail.locations.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] text-zinc-500 font-medium mb-1.5">Linked Business Locations</p>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {detail.locations.map((loc) => (
                  <div key={loc.id} className="flex items-center justify-between px-3 py-2">
                    <p className="text-sm text-zinc-300">{loc.company_name}</p>
                    <p className="text-[11px] text-zinc-500">{loc.name || loc.city}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
