import { type Dispatch, type SetStateAction } from 'react'
import { Button, Input, Select } from '../../ui'
import type { LinkHistoryEntry, LocationLink, LocationRow } from './types'
import { locationLabel } from './helpers'
import { LinkRow } from './LinkRow'

interface LocationLinksSectionProps {
  locations: LocationRow[]
  links: LocationLink[]
  pickable: LocationRow[]
  pickLoc: string
  setPickLoc: Dispatch<SetStateAction<string>>
  genLoading: boolean
  generateForLocation: (locationId: string, withLimits?: boolean) => void
  genMaxUses: string
  setGenMaxUses: Dispatch<SetStateAction<string>>
  genExpiry: string
  setGenExpiry: Dispatch<SetStateAction<string>>
  linkSearch: string
  setLinkSearch: Dispatch<SetStateAction<string>>
  linkQuery: string
  activeLinks: LocationLink[]
  inactiveLinks: LocationLink[]
  inactiveOpen: boolean
  setInactiveOpen: Dispatch<SetStateAction<boolean>>
  qrOpen: string | null
  setQrOpen: Dispatch<SetStateAction<string | null>>
  histOpen: string | null
  histData: Record<string, LinkHistoryEntry[]>
  toggleHistory: (id: string) => void
  revokeLink: (id: string) => void
  downloadPoster: (path: string, filename: string) => void
}

export function LocationLinksSection(props: LocationLinksSectionProps) {
  const {
    locations, pickable, pickLoc, setPickLoc, genLoading, generateForLocation,
    genMaxUses, setGenMaxUses, genExpiry, setGenExpiry,
    links, linkSearch, setLinkSearch, linkQuery, activeLinks, inactiveLinks,
    inactiveOpen, setInactiveOpen,
    qrOpen, setQrOpen, histOpen, histData, toggleHistory, revokeLink, downloadPoster,
  } = props

  const renderLinkRow = (l: LocationLink) => (
    <LinkRow
      key={l.id}
      l={l}
      qrOpen={qrOpen}
      setQrOpen={setQrOpen}
      histOpen={histOpen}
      histData={histData}
      toggleHistory={toggleHistory}
      generateForLocation={generateForLocation}
      revokeLink={revokeLink}
      downloadPoster={downloadPoster}
    />
  )

  return (
    <div className="space-y-3">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Location-specific links</p>
      <p className="text-[11px] text-zinc-500">
        A unique URL / QR per site. Opens the full intake form with the location locked — the reporter just
        adds details and their name. Reusable until revoked or expired; regenerate to rotate the token if it leaks.
      </p>

      {locations.length === 0 ? (
        <p className="text-[11px] text-zinc-500">Add a location in Settings → Locations to create a link.</p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Select
                label="Location"
                options={[
                  { value: '', label: pickable.length ? 'Select a location…' : 'All locations have links' },
                  ...pickable.map((l) => ({ value: l.id, label: locationLabel(l) })),
                ]}
                value={pickLoc}
                onChange={(e) => setPickLoc(e.target.value)}
              />
            </div>
            <Button size="sm" disabled={genLoading || !pickLoc} onClick={() => generateForLocation(pickLoc, true)}>
              Generate
            </Button>
          </div>
          {/* Optional limits — blank = unlimited uses / never expires. */}
          <div className="flex items-end gap-2">
            <div className="w-32">
              <Input
                label="Max uses"
                type="number"
                min={1}
                placeholder="Unlimited"
                value={genMaxUses}
                onChange={(e) => setGenMaxUses(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Input
                label="Expires"
                type="date"
                value={genExpiry}
                onChange={(e) => setGenExpiry(e.target.value)}
              />
            </div>
          </div>
        </div>
      )}

      {links.length > 0 && (
        <div className="space-y-3">
          <Input
            placeholder="Search locations…"
            value={linkSearch}
            onChange={(e) => setLinkSearch(e.target.value)}
          />

          <div className="space-y-2">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Active ({activeLinks.length})
            </p>
            {activeLinks.length === 0 ? (
              <p className="text-[11px] text-zinc-600">
                {linkQuery ? 'No matches.' : 'No active links.'}
              </p>
            ) : (
              <div className="space-y-2">{activeLinks.map(renderLinkRow)}</div>
            )}
          </div>

          {inactiveLinks.length > 0 && (
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setInactiveOpen((v) => !v)}
                className="text-[10px] font-bold text-zinc-500 hover:text-zinc-300 uppercase tracking-widest"
              >
                {inactiveOpen ? 'Hide' : 'Show'} inactive ({inactiveLinks.length})
              </button>
              {inactiveOpen && (
                <div className="space-y-2">{inactiveLinks.map(renderLinkRow)}</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
