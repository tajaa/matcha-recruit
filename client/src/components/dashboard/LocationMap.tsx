import { useMemo, useState } from 'react'
import { ComposableMap, Geographies, Geography, Marker } from 'react-simple-maps'
import type { BusinessLocation, HeatMapCell } from '../../types/dashboard'

interface Props {
  locations: BusinessLocation[]
  heatMap: HeatMapCell[]
}

const GEO_URL = '/states-10m.json'

// [lon, lat] for react-simple-maps Marker coordinates
const CITY_LONLAT: Record<string, [number, number]> = {
  'seattle_wa':           [-122.33, 47.61],
  'portland_or':          [-122.68, 45.52],
  'san francisco_ca':     [-122.42, 37.77],
  'oakland_ca':           [-122.27, 37.80],
  'san jose_ca':          [-121.89, 37.34],
  'los angeles_ca':       [-118.24, 34.05],
  'san diego_ca':         [-117.16, 32.72],
  'sacramento_ca':        [-121.49, 38.58],
  'fresno_ca':            [-119.77, 36.74],
  'las vegas_nv':         [-115.14, 36.17],
  'reno_nv':              [-119.81, 39.53],
  'phoenix_az':           [-112.07, 33.45],
  'tucson_az':            [-110.97, 32.22],
  'albuquerque_nm':       [-106.65, 35.08],
  'santa fe_nm':          [-105.94, 35.69],
  'denver_co':            [-104.99, 39.74],
  'colorado springs_co':  [-104.82, 38.83],
  'salt lake city_ut':    [-111.89, 40.76],
  'boise_id':             [-116.20, 43.62],
  'billings_mt':          [-108.50, 45.78],
  'casper_wy':            [-106.31, 42.87],
  'chicago_il':           [-87.63, 41.88],
  'milwaukee_wi':         [-87.91, 43.04],
  'minneapolis_mn':       [-93.27, 44.98],
  'st. paul_mn':          [-93.09, 44.95],
  'detroit_mi':           [-83.05, 42.33],
  'grand rapids_mi':      [-85.67, 42.96],
  'indianapolis_in':      [-86.16, 39.77],
  'columbus_oh':          [-82.99, 39.96],
  'cleveland_oh':         [-81.69, 41.50],
  'cincinnati_oh':        [-84.51, 39.10],
  'kansas city_mo':       [-94.58, 39.10],
  'st. louis_mo':         [-90.20, 38.63],
  'omaha_ne':             [-95.93, 41.26],
  'lincoln_ne':           [-96.68, 40.81],
  'des moines_ia':        [-93.61, 41.59],
  'sioux falls_sd':       [-96.73, 43.55],
  'fargo_nd':             [-96.79, 46.88],
  'wichita_ks':           [-97.34, 37.69],
  'dallas_tx':            [-96.80, 32.78],
  'fort worth_tx':        [-97.33, 32.76],
  'houston_tx':           [-95.37, 29.76],
  'san antonio_tx':       [-98.49, 29.42],
  'austin_tx':            [-97.74, 30.27],
  'el paso_tx':           [-106.44, 31.76],
  'lubbock_tx':           [-101.85, 33.58],
  'tulsa_ok':             [-95.99, 36.15],
  'oklahoma city_ok':     [-97.52, 35.47],
  'memphis_tn':           [-90.05, 35.15],
  'nashville_tn':         [-86.78, 36.16],
  'knoxville_tn':         [-83.92, 35.96],
  'atlanta_ga':           [-84.39, 33.75],
  'savannah_ga':          [-81.10, 32.08],
  'charlotte_nc':         [-80.84, 35.23],
  'raleigh_nc':           [-78.64, 35.78],
  'greensboro_nc':        [-79.79, 36.07],
  'columbia_sc':          [-81.03, 34.00],
  'charleston_sc':        [-79.93, 32.78],
  'new orleans_la':       [-90.07, 29.95],
  'baton rouge_la':       [-91.19, 30.45],
  'birmingham_al':        [-86.80, 33.52],
  'mobile_al':            [-88.04, 30.69],
  'jackson_ms':           [-90.18, 32.30],
  'miami_fl':             [-80.19, 25.76],
  'orlando_fl':           [-81.38, 28.54],
  'tampa_fl':             [-82.46, 27.95],
  'jacksonville_fl':      [-81.66, 30.33],
  'tallahassee_fl':       [-84.28, 30.44],
  'richmond_va':          [-77.44, 37.54],
  'virginia beach_va':    [-75.98, 36.85],
  'washington_dc':        [-77.04, 38.91],
  'baltimore_md':         [-76.61, 39.29],
  'philadelphia_pa':      [-75.17, 39.95],
  'pittsburgh_pa':        [-79.99, 40.44],
  'new york_ny':          [-74.01, 40.71],
  'buffalo_ny':           [-78.88, 42.89],
  'albany_ny':            [-73.76, 42.65],
  'boston_ma':             [-71.06, 42.36],
  'worcester_ma':         [-71.80, 42.26],
  'providence_ri':        [-71.41, 41.82],
  'hartford_ct':          [-72.68, 41.76],
  'bridgeport_ct':        [-73.20, 41.17],
  'newark_nj':            [-74.17, 40.74],
  'trenton_nj':           [-74.76, 40.22],
  'wilmington_de':        [-75.55, 39.74],
  'dover_de':             [-75.52, 39.16],
  'annapolis_md':         [-76.49, 38.98],
  'manchester_nh':        [-71.46, 42.99],
  'portland_me':          [-70.25, 43.66],
  'burlington_vt':        [-73.21, 44.48],
}

// Fallback: state centroid [lon, lat]
const STATE_LONLAT: Record<string, [number, number]> = {
  wa: [-120.74, 47.75], or: [-120.55, 43.80], ca: [-119.42, 36.78],
  nv: [-116.42, 38.80], az: [-111.09, 34.05], id: [-114.74, 44.07],
  mt: [-109.53, 46.88], wy: [-107.29, 43.08], co: [-105.78, 39.55],
  nm: [-105.87, 34.52], ut: [-111.09, 39.32], nd: [-101.00, 47.55],
  sd: [-99.90, 43.97],  ne: [-99.90, 41.49],  ks: [-98.48, 38.50],
  ok: [-97.09, 35.47],  tx: [-99.90, 31.97],  mn: [-94.64, 46.73],
  ia: [-93.10, 41.88],  mo: [-91.83, 38.57],  ar: [-91.83, 35.20],
  la: [-92.33, 30.98],  wi: [-89.62, 43.78],  il: [-89.40, 40.63],
  mi: [-84.71, 44.35],  in: [-86.13, 40.27],  oh: [-82.91, 40.42],
  ky: [-84.27, 37.84],  tn: [-86.58, 35.52],  ms: [-89.53, 32.35],
  al: [-86.90, 32.32],  ga: [-83.64, 32.17],  fl: [-81.52, 27.66],
  sc: [-81.16, 33.84],  nc: [-79.01, 35.76],  va: [-79.35, 37.43],
  wv: [-80.95, 38.60],  pa: [-77.20, 41.20],  ny: [-75.00, 43.00],
  nj: [-74.41, 40.06],  de: [-75.51, 38.91],  md: [-76.64, 39.05],
  dc: [-77.04, 38.91],  ct: [-72.76, 41.60],  ri: [-71.48, 41.58],
  ma: [-71.53, 42.41],  vt: [-72.58, 44.56],  nh: [-71.57, 43.19],
  me: [-69.45, 45.25],
}

type Tier = 'critical' | 'high' | 'medium' | 'clear'

const TIER_COLOR: Record<Tier, string> = {
  critical: '#b45309',
  high:     '#b45309',
  medium:   '#d97706',
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

function parseLocationName(name: string): { city: string; state: string } {
  const comma = name.lastIndexOf(',')
  if (comma === -1) return { city: name.trim(), state: '' }
  return {
    city: name.slice(0, comma).trim(),
    state: name.slice(comma + 1).trim(),
  }
}

function shortLabel(name: string): string {
  const { city } = parseLocationName(name)
  const c = city.toLowerCase()
  if (c === 'san francisco') return 'SF'
  if (c === 'los angeles') return 'LA'
  if (c === 'new york') return 'NY'
  if (c === 'washington') return 'DC'
  if (c === 'new orleans') return 'NOLA'
  if (c === 'san antonio') return 'SA'
  if (c === 'salt lake city') return 'SLC'
  if (c === 'oklahoma city') return 'OKC'
  if (c === 'colorado springs') return 'COS'
  if (c === 'virginia beach') return 'VA BCH'
  if (c === 'jacksonville') return 'JAX'
  if (c === 'minneapolis') return 'MPLS'
  if (c === 'indianapolis') return 'INDY'
  return city.toUpperCase()
}

export function LocationMap({ locations, heatMap }: Props) {
  const [tooltip, setTooltip] = useState<{ name: string; tier: Tier } | null>(null)

  const { severityMap, globalFloor } = useMemo(() => {
    const map = new Map<string, Tier>()
    const order: Record<string, number> = { critical: 0, high: 1, medium: 2, clear: 3 }
    const knownKeys = new Set(
      locations.map(loc => locKey(
        loc.city || parseLocationName(loc.name).city,
        loc.state || parseLocationName(loc.name).state,
      ))
    )
    let floor: Tier = 'clear'
    for (const cell of heatMap) {
      const { city, state } = parseLocationName(cell.location)
      const key = locKey(city, state)
      const tier = SEV_TIER[cell.worst_severity] ?? 'medium'
      if (knownKeys.has(key)) {
        const existing = map.get(key)
        if (!existing || order[tier] < order[existing]) map.set(key, tier)
      } else {
        if (order[tier] < order[floor]) floor = tier
      }
    }
    return { severityMap: map, globalFloor: floor }
  }, [heatMap, locations])

  const dots = useMemo(() => {
    const tierOrder: Record<Tier, number> = { critical: 0, high: 1, medium: 2, clear: 3 }
    const seen = new Map<string, { name: string; coords: [number, number]; tier: Tier; index: number }>()
    locations.forEach((loc, i) => {
      const city = loc.city || parseLocationName(loc.name).city
      const state = loc.state || parseLocationName(loc.name).state
      const key = locKey(city, state)
      const coords = CITY_LONLAT[key] ?? STATE_LONLAT[state.toLowerCase()] ?? null
      if (!coords) return
      const specific = severityMap.get(key) ?? 'clear'
      const tier = tierOrder[specific] <= tierOrder[globalFloor] ? specific : globalFloor
      const existing = seen.get(key)
      if (!existing || tierOrder[tier] < tierOrder[existing.tier]) {
        seen.set(key, { name: loc.name, coords, tier, index: i })
      }
    })
    return [...seen.entries()].map(([, v], i) => ({ ...v, index: i }))
  }, [locations, severityMap, globalFloor])

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
        className="relative rounded-xl overflow-hidden select-none"
        style={{ background: '#0a0a0a' }}
      >
        <ComposableMap
          projection="geoAlbersUsa"
          projectionConfig={{ scale: 600 }}
          width={800}
          height={350}
          style={{ width: '100%', height: 'auto' }}
        >
          {/* State boundaries — wireframe style */}
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rpiProperties?.name || geo.id}
                  geography={geo}
                  fill="rgba(255,255,255,0.015)"
                  stroke="#a1a1aa"
                  strokeWidth={0.3}
                  style={{
                    default: { outline: 'none' },
                    hover: { outline: 'none', fill: 'rgba(255,255,255,0.04)' },
                    pressed: { outline: 'none' },
                  }}
                />
              ))
            }
          </Geographies>

          {/* Location markers */}
          {dots.map((dot) => {
            const color = dotColor(dot.tier)
            const label = shortLabel(dot.name)
            return (
              <Marker
                key={`${dot.name}_${dot.index}`}
                coordinates={dot.coords}
                onMouseEnter={() => setTooltip({ name: dot.name, tier: dot.tier })}
                onMouseLeave={() => setTooltip(null)}
              >
                {/* Pulse halo */}
                <circle r={12} fill={color} opacity={0.15}>
                  <animate
                    attributeName="r"
                    from="6"
                    to="18"
                    dur="2.6s"
                    begin={`${(dot.index % 7) * 0.38}s`}
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    from="0.4"
                    to="0"
                    dur="2.6s"
                    begin={`${(dot.index % 7) * 0.38}s`}
                    repeatCount="indefinite"
                  />
                </circle>
                {/* Outer ring */}
                <circle r={6} fill="none" stroke={color} strokeWidth={0.5} opacity={0.4} />
                {/* Inner dot */}
                <circle r={3} fill={color} style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
                {/* Connection line */}
                <line x1={0} y1={-4} x2={0} y2={-16} stroke={color} strokeWidth={0.5} opacity={0.4} />
                {/* City label */}
                <text
                  y={-20}
                  textAnchor="middle"
                  style={{
                    fontFamily: '"Space Mono", "SF Mono", monospace',
                    fontSize: '7px',
                    fontWeight: 400,
                    fill: '#ffffff',
                    opacity: 0.7,
                    letterSpacing: '0.18em',
                  }}
                >
                  {label}
                </text>
              </Marker>
            )
          })}
        </ComposableMap>

        {/* Tooltip overlay */}
        {tooltip && (
          <div
            className="fixed z-50 pointer-events-none rounded border border-zinc-700/60 bg-zinc-900/95 px-2.5 py-1.5 text-[10px] text-white whitespace-nowrap font-mono backdrop-blur-sm"
            style={{
              left: 'var(--mouse-x, 50%)',
              top: 'var(--mouse-y, 50%)',
              transform: 'translate(-50%, -140%)',
            }}
          >
            {tooltip.name}
            {tooltip.tier !== 'clear' && (
              <span className="ml-1.5 uppercase tracking-wider text-[9px]" style={{ color: dotColor(tooltip.tier) }}>
                [{tooltip.tier}]
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
