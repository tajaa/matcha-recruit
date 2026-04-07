import { useMemo, useState } from 'react'
import type { BusinessLocation, HeatMapCell } from '../../types/dashboard'

interface Props {
  locations: BusinessLocation[]
  heatMap: HeatMapCell[]
}

// [x%, y%] — x: 0=west, 100=east  |  y: 0=north, 100=south
// Bounding box is the contiguous US (~2.5:1 ratio)
const CITY_COORDS: Record<string, [number, number]> = {
  // West Coast
  'seattle_wa':           [10, 7],
  'portland_or':          [9, 14],
  'san francisco_ca':     [7, 30],
  'oakland_ca':           [7, 31],
  'san jose_ca':          [7, 33],
  'los angeles_ca':       [9, 38],
  'san diego_ca':         [10, 42],
  'sacramento_ca':        [8, 27],
  'fresno_ca':            [8, 34],
  // Southwest
  'las vegas_nv':         [13, 36],
  'reno_nv':              [11, 24],
  'phoenix_az':           [16, 44],
  'tucson_az':            [17, 48],
  'albuquerque_nm':       [20, 44],
  'santa fe_nm':          [20, 41],
  // Mountain
  'denver_co':            [23, 29],
  'colorado springs_co':  [24, 32],
  'salt lake city_ut':    [17, 26],
  'boise_id':             [15, 16],
  'billings_mt':          [21, 11],
  'casper_wy':            [21, 20],
  // Midwest
  'chicago_il':           [55, 20],
  'milwaukee_wi':         [56, 16],
  'minneapolis_mn':       [49, 12],
  'st. paul_mn':          [50, 12],
  'detroit_mi':           [61, 17],
  'grand rapids_mi':      [59, 17],
  'indianapolis_in':      [58, 26],
  'columbus_oh':          [63, 24],
  'cleveland_oh':         [64, 19],
  'cincinnati_oh':        [62, 28],
  'kansas city_mo':       [46, 31],
  'st. louis_mo':         [52, 30],
  'omaha_ne':             [41, 23],
  'lincoln_ne':           [41, 25],
  'des moines_ia':        [49, 22],
  'sioux falls_sd':       [40, 16],
  'fargo_nd':             [41, 9],
  'wichita_ks':           [42, 35],
  // South / Texas
  'dallas_tx':            [43, 50],
  'fort worth_tx':        [42, 50],
  'houston_tx':           [45, 57],
  'san antonio_tx':       [42, 58],
  'austin_tx':            [43, 55],
  'el paso_tx':           [27, 52],
  'lubbock_tx':           [36, 47],
  'tulsa_ok':             [45, 42],
  'oklahoma city_ok':     [44, 44],
  // Southeast
  'memphis_tn':           [54, 39],
  'nashville_tn':         [58, 37],
  'knoxville_tn':         [62, 36],
  'atlanta_ga':           [61, 46],
  'savannah_ga':          [65, 50],
  'charlotte_nc':         [66, 38],
  'raleigh_nc':           [68, 36],
  'greensboro_nc':        [67, 36],
  'columbia_sc':          [66, 43],
  'charleston_sc':        [67, 46],
  'new orleans_la':       [52, 60],
  'baton rouge_la':       [51, 58],
  'birmingham_al':        [58, 47],
  'mobile_al':            [57, 53],
  'jackson_ms':           [53, 50],
  'miami_fl':             [66, 68],
  'orlando_fl':           [64, 62],
  'tampa_fl':             [63, 62],
  'jacksonville_fl':      [64, 55],
  'tallahassee_fl':       [61, 57],
  // Mid-Atlantic / Northeast
  'richmond_va':          [71, 31],
  'virginia beach_va':    [74, 31],
  'washington_dc':        [73, 27],
  'baltimore_md':         [74, 26],
  'philadelphia_pa':      [76, 23],
  'pittsburgh_pa':        [67, 22],
  'new york_ny':          [78, 21],
  'buffalo_ny':           [69, 17],
  'albany_ny':            [77, 16],
  'boston_ma':            [82, 14],
  'worcester_ma':         [81, 15],
  'providence_ri':        [82, 17],
  'hartford_ct':          [80, 18],
  'bridgeport_ct':        [79, 19],
  'newark_nj':            [77, 22],
  'trenton_nj':           [76, 24],
  'wilmington_de':        [75, 25],
  'dover_de':             [76, 26],
  'annapolis_md':         [74, 27],
  'manchester_nh':        [80, 12],
  'portland_me':          [82, 10],
  'burlington_vt':        [79, 12],
}

const STATE_CENTROIDS: Record<string, [number, number]> = {
  wa: [11, 9],  or: [10, 17], ca: [9, 33],  nv: [13, 28],
  az: [17, 44], id: [15, 16], mt: [20, 10], wy: [21, 20],
  co: [23, 29], nm: [20, 44], ut: [17, 26], nd: [39, 9],
  sd: [39, 17], ne: [40, 24], ks: [41, 33], ok: [43, 44],
  tx: [40, 53], mn: [48, 13], ia: [48, 22], mo: [50, 31],
  ar: [50, 43], la: [50, 57], wi: [54, 16], il: [54, 25],
  mi: [60, 15], in: [58, 25], oh: [63, 22], ky: [60, 33],
  tn: [58, 38], ms: [53, 49], al: [58, 48], ga: [61, 47],
  fl: [64, 62], sc: [66, 43], nc: [66, 36], va: [71, 30],
  wv: [67, 26], pa: [71, 21], ny: [75, 17], nj: [77, 23],
  de: [76, 25], md: [73, 26], dc: [73, 27], ct: [80, 18],
  ri: [82, 17], ma: [81, 14], vt: [79, 11], nh: [80, 11],
  me: [83, 8],
}

// Rough continental US clip-path polygon (% coordinates)
const US_CLIP = `polygon(
  5% 12%, 5% 20%, 7% 28%, 6% 38%, 8% 46%, 11% 48%,
  13% 52%, 18% 52%, 24% 56%, 30% 64%, 38% 68%,
  46% 68%, 52% 65%, 56% 70%, 62% 74%, 66% 72%,
  68% 60%, 72% 44%, 76% 32%, 80% 24%, 84% 16%,
  82% 10%, 76% 8%, 62% 6%, 46% 4%, 32% 4%,
  20% 6%, 10% 8%, 5% 12%
)`

const DOT_GRID = 'radial-gradient(circle, rgba(161,161,170,0.18) 1px, transparent 1px)'

type Tier = 'critical' | 'high' | 'medium' | 'clear'

const TIER_COLOR: Record<Tier, string> = {
  critical: '#ce8060',
  high:     '#ce8060',
  medium:   '#c8a850',
  clear:    '#4a8a52',
}

const SEV_TIER: Record<string, Tier> = {
  critical: 'critical',
  high:     'high',
  medium:   'medium',
  low:      'clear',
}

function dotColor(tier: Tier): string {
  return TIER_COLOR[tier]
}

function locKey(city: string, state: string): string {
  return `${city.trim().toLowerCase()}_${state.trim().toLowerCase()}`
}

// Parse "Los Angeles, CA" → { city: "Los Angeles", state: "CA" }
function parseLocationName(name: string): { city: string; state: string } {
  const comma = name.lastIndexOf(',')
  if (comma === -1) return { city: name.trim(), state: '' }
  return {
    city: name.slice(0, comma).trim(),
    state: name.slice(comma + 1).trim(),
  }
}

export function LocationMap({ locations, heatMap }: Props) {
  const [tooltip, setTooltip] = useState<{ name: string; tier: Tier; x: number; y: number } | null>(null)

  // Build severity map keyed by city_state from heatMap Locations group
  const severityMap = useMemo(() => {
    const map = new Map<string, Tier>()
    const order: Record<string, number> = { critical: 0, high: 1, medium: 2, clear: 3 }
    for (const cell of heatMap) {
      if (cell.group !== 'Locations') continue
      const { city, state } = parseLocationName(cell.location)
      const key = locKey(city, state)
      const tier = SEV_TIER[cell.worst_severity] ?? 'medium'
      const existing = map.get(key)
      if (!existing || order[tier] < order[existing]) {
        map.set(key, tier)
      }
    }
    return map
  }, [heatMap])

  // Resolve coordinates for each location, deduplicating by city+state key
  const dots = useMemo(() => {
    const tierOrder: Record<Tier, number> = { critical: 0, high: 1, medium: 2, clear: 3 }
    const seen = new Map<string, { name: string; coords: [number, number]; tier: Tier; index: number }>()

    locations.forEach((loc, i) => {
      const city = loc.city || parseLocationName(loc.name).city
      const state = loc.state || parseLocationName(loc.name).state
      const key = locKey(city, state)
      const coords = CITY_COORDS[key] ?? STATE_CENTROIDS[state.toLowerCase()] ?? null
      if (!coords) return
      const tier = severityMap.get(key) ?? 'clear'
      const existing = seen.get(key)
      if (!existing || tierOrder[tier] < tierOrder[existing.tier]) {
        seen.set(key, { name: loc.name, coords, tier, index: i })
      }
    })

    return [...seen.entries()].map(([, v], i) => ({ ...v, index: i }))
  }, [locations, severityMap])

  if (dots.length === 0) return null

  return (
    <div className="mb-5">
      <div className="flex items-center gap-4 mb-2.5">
        <h3 className="text-[11px] font-medium text-vsc-text/50 uppercase tracking-wider">Location Coverage</h3>
        <div className="flex items-center gap-3 text-[9px] text-vsc-text/40">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: TIER_COLOR.critical }} />Critical/High
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: TIER_COLOR.medium }} />Medium
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: TIER_COLOR.clear }} />All Clear
          </span>
        </div>
      </div>

      {/* Map container */}
      <div
        className="relative w-full rounded-xl border border-vsc-border overflow-hidden select-none"
        style={{
          paddingBottom: '40%',
          background: '#191919',
          backgroundImage: DOT_GRID,
          backgroundSize: '18px 18px',
        }}
      >
        {/* US shape tint */}
        <div
          className="absolute inset-0"
          style={{
            clipPath: US_CLIP,
            background: 'rgba(37,37,38,0.55)',
          }}
        />

        {/* Dots */}
        {dots.map((dot) => {
          const color = dotColor(dot.tier)
          const delay = `${(dot.index % 7) * 0.38}s`
          return (
            <div
              key={`${dot.city}_${dot.state}`}
              className="absolute"
              style={{ left: `${dot.coords[0]}%`, top: `${dot.coords[1]}%` }}
            >
              {/* Pulsing halo — centering wrapper keeps halo in place across animation frames */}
              <div
                className="absolute pointer-events-none"
                style={{ transform: 'translate(-50%, -50%)' }}
              >
                <div
                  className="w-4 h-4 rounded-full"
                  style={{
                    background: color,
                    animation: `map-pulse 2.6s ease-out ${delay} infinite`,
                  }}
                />
              </div>
              {/* Solid inner dot */}
              <div
                className="absolute w-2 h-2 rounded-full cursor-default"
                style={{
                  transform: 'translate(-50%, -50%)',
                  background: color,
                  boxShadow: `0 0 5px ${color}, 0 0 2px ${color}`,
                }}
                onMouseEnter={() => setTooltip({ name: dot.name, tier: dot.tier, x: dot.coords[0], y: dot.coords[1] })}
                onMouseLeave={() => setTooltip(null)}
              />
            </div>
          )
        })}

        {/* Tooltip */}
        {tooltip && (
          <div
            className="absolute z-20 pointer-events-none rounded-lg border border-vsc-border bg-vsc-panel px-2.5 py-1.5 text-[10px] text-vsc-text whitespace-nowrap"
            style={{
              left: `${tooltip.x}%`,
              top: `${tooltip.y}%`,
              transform: 'translate(-50%, -160%)',
            }}
          >
            <span className="font-medium">{tooltip.name}</span>
            {tooltip.tier !== 'clear' && (
              <span className="ml-2 capitalize" style={{ color: dotColor(tooltip.tier) }}>
                {tooltip.tier}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
