import { Badge } from '../../../../components/ui'
import { LABEL } from '../../../../components/ui/typography'
import { ComplianceLocationList } from '../../../../components/compliance/ComplianceLocationList'
import { FacilityProfileBanner } from '../../../../components/compliance/FacilityProfileBanner'
import { PANEL } from './constants'
import type { BusinessLocation } from '../../../../types/compliance'

type LocationsTabProps = {
  locations: BusinessLocation[]
  locationsLoading: boolean
  selectedId: string | null
  onSelect: (id: string | null) => void
  onEdit: (loc: BusinessLocation) => void
  onDelete: (locId: string) => void
  onAdd: () => void
  readOnly: boolean
  loadLocations: () => Promise<void> | void
}

export function LocationsTab({
  locations,
  locationsLoading,
  selectedId,
  onSelect,
  onEdit,
  onDelete,
  onAdd,
  readOnly,
  loadLocations,
}: LocationsTabProps) {
  const selectedLoc = locations.find((l) => l.id === selectedId)

  return (
    // Locations Tab. This used to carry its own frame — a second
    // bg-zinc-950 border-white/[0.06] shell nested inside the page's new
    // one. Reduced to the split + divider it actually needs.
    <div className="-m-5 md:grid md:grid-cols-3">
      <div className="border-b border-white/[0.06] p-4 md:col-span-1 md:border-b-0 md:border-r">
        <ComplianceLocationList
          locations={locations}
          selectedId={selectedId}
          onSelect={onSelect}
          onEdit={onEdit}
          onDelete={onDelete}
          onAdd={onAdd}
          loading={locationsLoading}
          readOnly={readOnly}
        />
      </div>

      <div className="p-4 md:col-span-2">
        {!selectedId ? (
          <div className="flex items-center justify-center h-40">
            <p className="text-sm text-zinc-600">Select a location to view details</p>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-base font-medium text-zinc-100">
                  {selectedLoc?.city}, {selectedLoc?.state}
                  {selectedLoc?.name && <span className="text-zinc-500 ml-2 text-sm">({selectedLoc.name})</span>}
                </h2>
                <div className="flex items-center gap-2 mt-0.5">
                  {selectedLoc?.source === 'employee_derived' && (
                    <Badge variant="neutral">
                      <span className="text-purple-400">Auto-created from employee</span>
                    </Badge>
                  )}
                  {selectedLoc && selectedLoc.employee_count > 0 && (
                    <span className="text-[11px] text-zinc-500">{selectedLoc.employee_count} employees</span>
                  )}
                </div>
              </div>
            </div>

            <FacilityProfileBanner
              locationId={selectedId}
              facilityAttributes={selectedLoc?.facility_attributes}
              onUpdated={() => loadLocations()}
              allLocations={locations}
              source={selectedLoc?.source}
              readOnly={readOnly}
            />

            <div className={PANEL}>
              <h3 className={`${LABEL} mb-3`}>Location Details</h3>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-zinc-500 text-xs">City</dt>
                  <dd className="text-zinc-200">{selectedLoc?.city}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500 text-xs">State</dt>
                  <dd className="text-zinc-200">{selectedLoc?.state}</dd>
                </div>
                {selectedLoc?.county && (
                  <div>
                    <dt className="text-zinc-500 text-xs">County</dt>
                    <dd className="text-zinc-200">{selectedLoc.county}</dd>
                  </div>
                )}
                {selectedLoc?.zipcode && (
                  <div>
                    <dt className="text-zinc-500 text-xs">ZIP Code</dt>
                    <dd className="text-zinc-200">{selectedLoc.zipcode}</dd>
                  </div>
                )}
                {selectedLoc?.address && (
                  <div className="col-span-2">
                    <dt className="text-zinc-500 text-xs">Address</dt>
                    <dd className="text-zinc-200">{selectedLoc.address}</dd>
                  </div>
                )}
                <div>
                  <dt className="text-zinc-500 text-xs">Requirements</dt>
                  <dd className="text-zinc-200">{selectedLoc?.requirements_count ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500 text-xs">Employees</dt>
                  <dd className="text-zinc-200">{selectedLoc?.employee_count ?? 0}</dd>
                </div>
                {selectedLoc?.employee_names && selectedLoc.employee_names.length > 0 && (
                  <div className="col-span-2">
                    <dt className="text-zinc-500 text-xs mb-1">Assigned Employees</dt>
                    <dd className="flex flex-wrap gap-1.5">
                      {selectedLoc.employee_names.map((name) => (
                        <span key={name} className="text-xs px-2 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">{name}</span>
                      ))}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
