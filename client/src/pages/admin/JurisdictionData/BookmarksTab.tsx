import { fmtDate } from '../../../components/admin/jurisdiction/utils'
import type { BookmarkedReq, FlatCity } from '../../../components/admin/jurisdiction/types'
import { getShortLabel } from './helpers'

interface BookmarksTabProps {
  bookmarks: BookmarkedReq[]
  loading: boolean
  allCities: FlatCity[]
  onNavigateToCity: (flat: FlatCity) => void
  onToggleBookmark: (reqId: string) => void
}

export default function BookmarksTab({ bookmarks, loading, allCities, onNavigateToCity, onToggleBookmark }: BookmarksTabProps) {
  // Group bookmarks by state → city
  const grouped: Record<string, Record<string, BookmarkedReq[]>> = {}
  let stateCount = 0
  for (const b of bookmarks) {
    if (!grouped[b.state]) { grouped[b.state] = {}; stateCount++ }
    if (!grouped[b.state][b.city]) grouped[b.state][b.city] = []
    grouped[b.state][b.city].push(b)
  }
  return (
    <div>
      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : bookmarks.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">No bookmarked requirements. Bookmark items from the Jurisdictions page.</p>
        </div>
      ) : (
        <>
          <p className="text-[11px] text-zinc-500 mb-2">
            {bookmarks.length} bookmarked requirement{bookmarks.length !== 1 ? 's' : ''} across {stateCount} state{stateCount !== 1 ? 's' : ''}
          </p>
          <div className="border border-zinc-800 rounded-lg max-h-[70vh] overflow-y-auto">
            {Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b)).map(([st, cities]) => (
              <div key={st}>
                <div className="px-4 pt-3 pb-1 bg-zinc-900/50 sticky top-0">
                  <p className="text-xs uppercase tracking-wide text-zinc-400 font-medium">{st}</p>
                </div>
                {Object.entries(cities).sort(([a], [b]) => a.localeCompare(b)).map(([cityName, reqs]) => (
                  <div key={cityName}>
                    <div className="px-4 pt-2 pb-1">
                      <button
                        type="button"
                        className="text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
                        onClick={() => {
                          const cityFlat = allCities.find(c => c.city === cityName && c.stateName === st)
                          if (cityFlat) {
                            onNavigateToCity(cityFlat)
                          }
                        }}
                      >
                        {cityName} →
                      </button>
                    </div>
                    <div className="divide-y divide-zinc-800/60">
                      {reqs.map((req) => (
                        <div key={req.id} className="flex items-start gap-3 px-4 py-2.5">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-zinc-200">{req.title}</p>
                            {req.description && (
                              <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{req.description}</p>
                            )}
                            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">
                                {getShortLabel(req.category)}
                              </span>
                              <span className="text-[11px] text-zinc-500">{req.jurisdiction_level}</span>
                              {req.current_value && <span className="text-[11px] text-zinc-400">{req.current_value}</span>}
                              {req.effective_date && <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>}
                              {req.last_verified_at && <span className="text-[11px] text-zinc-600">verified {fmtDate(req.last_verified_at)}</span>}
                              {req.source_name && (
                                req.source_url
                                  ? <a href={req.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">{req.source_name}</a>
                                  : <span className="text-[11px] text-zinc-600">{req.source_name}</span>
                              )}
                            </div>
                          </div>
                          <button type="button" onClick={() => onToggleBookmark(req.id)}
                            className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors shrink-0">
                            Unbookmark
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
