import { useEffect, useState } from 'react'
import { Gauge, Loader2, ArrowUpRight, Sparkles, ListChecks, Check, Circle, MapPin, Ban } from 'lucide-react'
import { LABEL } from '../../components/ui/typography'
import { fetchRiskProfile, fetchRiskNarrative, fetchSubmissionReadiness, fetchVenueExposure, fetchExclusionGap } from '../../api/riskIndex'
import type { RiskNarrative } from '../../api/riskIndex'
import type { RiskIndex, SubmissionReadiness, VenueExposure, ExclusionGap } from '../../types/riskIndex'
import { RISK_BAND_TONE, RISK_CONFIDENCE_TONE, READINESS_BAND_TONE, VENUE_TIER_TONE, EXCLUSION_TONE } from '../../types/riskIndex'

const PANEL = 'rounded-lg border border-white/[0.06] bg-zinc-950'

export default function RiskProfile() {
  const [data, setData] = useState<RiskIndex | null>(null)
  const [loading, setLoading] = useState(true)
  const [narrative, setNarrative] = useState<RiskNarrative | null>(null)
  const [explaining, setExplaining] = useState(false)
  const [readiness, setReadiness] = useState<SubmissionReadiness | null>(null)
  const [venue, setVenue] = useState<VenueExposure | null>(null)
  const [exclusions, setExclusions] = useState<ExclusionGap | null>(null)
  const [profileError, setProfileError] = useState(false)
  const [readinessError, setReadinessError] = useState(false)
  const [venueError, setVenueError] = useState(false)
  const [exclusionError, setExclusionError] = useState(false)

  function loadRiskProfile() {
    setLoading(true)
    setProfileError(false)
    fetchRiskProfile().then(setData).catch(() => setProfileError(true)).finally(() => setLoading(false))
  }

  useEffect(() => {
    loadRiskProfile()
    fetchSubmissionReadiness().then(setReadiness).catch(() => setReadinessError(true))
    fetchVenueExposure().then(setVenue).catch(() => setVenueError(true))
    fetchExclusionGap().then(setExclusions).catch(() => setExclusionError(true))
  }, [])

  async function explain() {
    setExplaining(true)
    try { setNarrative(await fetchRiskNarrative()) } catch { /* noop */ } finally { setExplaining(false) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  }
  if (profileError) {
    return (
      <div className={`${PANEL} p-6 text-center`}>
        <p className="text-sm text-red-400">Couldn't load your risk profile.</p>
        <button onClick={loadRiskProfile} className="mt-2 text-xs text-emerald-400 hover:text-emerald-300 underline">Try again</button>
      </div>
    )
  }
  if (!data) return <div className="text-sm text-zinc-500">Risk profile unavailable.</div>

  const tone = data.band ? RISK_BAND_TONE[data.band] ?? 'text-zinc-200' : 'text-zinc-500'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <Gauge className="h-5 w-5 text-zinc-400" /> Risk Profile
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Your insurability at a glance — a composite of workers'-comp, EPL, and compliance posture. The cleaner this is, the better the terms your broker can win at renewal.</p>
      </div>

      {/* Index hero */}
      <div className={`${PANEL} p-6 flex items-center gap-8`}>
        <div className="text-center">
          <div className={`text-6xl font-light font-mono ${tone}`}>{data.index ?? '—'}</div>
          <div className={`text-xs uppercase tracking-widest font-bold mt-1 ${tone}`}>{data.band ?? 'no data'}</div>
          <div className="text-[10px] text-zinc-600 mt-0.5 flex items-center justify-center gap-1">
            / 100 risk index
            {data.index_confidence && data.index_confidence !== 'high' && (
              <span className={`inline-flex items-center gap-1 ${RISK_CONFIDENCE_TONE[data.index_confidence]}`} title="Some inputs behind this score rest on directional or thin data">
                <span className="h-1.5 w-1.5 rounded-full bg-current" /> {data.index_confidence} confidence
              </span>
            )}
          </div>
          {data.coverage != null && data.coverage < 1 && (
            <div className="text-[10px] text-zinc-600 mt-2 max-w-[11rem] mx-auto leading-relaxed">
              Based on {data.components.length} of {data.components.length + (data.components_missing?.length ?? 0)} signals ({Math.round(data.coverage * 100)}% of weight covered)
              {data.components_missing && data.components_missing.length > 0 && (
                <div className="mt-0.5">Not yet measured: {data.components_missing.map((c) => c.label).join(', ')}</div>
              )}
            </div>
          )}
        </div>
        <div className="flex-1 space-y-3">
          {data.components.map((c) => (
            <div key={c.key}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-zinc-300">{c.label} <span className="text-zinc-600">· wt {c.weight}</span></span>
                <span className="font-mono text-zinc-200">{c.score}/100</span>
              </div>
              <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                <div className={`h-full ${c.score >= 80 ? 'bg-emerald-500' : c.score >= 60 ? 'bg-zinc-400' : c.score >= 35 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${c.score}%` }} />
              </div>
              <div className="text-[11px] text-zinc-600 mt-0.5">{c.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Submission readiness — data→price completeness loop */}
      {readinessError && (
        <div className={`${PANEL} p-4`}>
          <p className="text-xs text-zinc-500">Couldn't load submission readiness.</p>
        </div>
      )}
      {readiness && (
        <div className={`${PANEL} p-5`}>
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className={`${LABEL} normal-case flex items-center gap-2`}>
                <ListChecks className="h-4 w-4 text-zinc-500" /> Submission readiness
              </h3>
              <p className="text-[11px] text-zinc-500 mt-0.5 max-w-xl">How underwriter-ready your WC + EPL data is. Completing these doesn't change your risk — it lets your broker articulate it, which is what wins tighter terms.</p>
            </div>
            <div className="text-right shrink-0">
              <div className={`text-3xl font-light font-mono ${READINESS_BAND_TONE[readiness.band] ?? 'text-zinc-200'}`}>{readiness.score}%</div>
              <div className={`text-[10px] uppercase tracking-widest font-bold ${READINESS_BAND_TONE[readiness.band] ?? 'text-zinc-500'}`}>{readiness.band}</div>
            </div>
          </div>
          <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden mb-3">
            <div className={`h-full ${readiness.score >= 80 ? 'bg-emerald-500' : readiness.score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${readiness.score}%` }} />
          </div>
          <div className="space-y-1">
            {readiness.items.map((it) => (
              <div key={it.key} className="flex items-start gap-2 py-1 border-b border-white/[0.04] last:border-0">
                {it.done
                  ? <Check className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                  : <Circle className="h-4 w-4 text-zinc-600 mt-0.5 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <span className={`text-sm ${it.done ? 'text-zinc-400' : 'text-zinc-200'}`}>{it.label}</span>
                  {!it.done && <p className="text-[11px] text-amber-400/80">{it.fix}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Venue exposure — casualty severity dimension (where you operate) */}
      {venueError && (
        <div className={`${PANEL} p-4`}>
          <p className="text-xs text-zinc-500">Couldn't load venue exposure.</p>
        </div>
      )}
      {venue && venue.locations.length > 0 && (
        <div className={`${PANEL} p-5`}>
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className={`${LABEL} normal-case flex items-center gap-2`}>
                <MapPin className="h-4 w-4 text-zinc-500" /> Venue exposure
              </h3>
              <p className="text-[11px] text-zinc-500 mt-0.5 max-w-xl">Where you operate drives casualty severity — underwriters weigh nuclear-verdict / plaintiff-friendly venues heavily. A directional flag, not a price.</p>
            </div>
            <div className="text-right shrink-0">
              <div className={`text-sm uppercase tracking-widest font-bold ${VENUE_TIER_TONE[venue.summary.worst_tier] ?? 'text-zinc-500'}`}>{venue.summary.worst_tier}</div>
              <div className="text-[10px] text-zinc-600">{venue.summary.severe_high_count} high-severity / {venue.summary.total_locations} loc</div>
            </div>
          </div>
          <div className="space-y-1">
            {venue.locations.map((l, i) => (
              <div key={`${l.state}-${l.county || ''}-${l.city || ''}-${i}`} className="flex items-center gap-3 py-1.5 border-b border-white/[0.04] last:border-0">
                <span className="text-sm text-zinc-200 flex-1">
                  {l.city || l.county || l.state}
                  {l.county && <span className="text-[11px] text-zinc-600 ml-2">{l.county}, {l.state}</span>}
                </span>
                <span className={`text-[10px] font-semibold uppercase ${VENUE_TIER_TONE[l.tier] ?? 'text-zinc-500'}`}>{l.tier}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600 mt-2">Source: ATRA Judicial Hellholes / US Chamber ILR / nuclear-verdict reporting — directional reputational flag.</p>
        </div>
      )}

      {/* Coverage exclusion exposure — emerging casualty exclusions */}
      {exclusionError && (
        <div className={`${PANEL} p-4`}>
          <p className="text-xs text-zinc-500">Couldn't load coverage exclusion exposure.</p>
        </div>
      )}
      {exclusions && exclusions.exclusions.length > 0 && (
        <div className={`${PANEL} p-5`}>
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className={`${LABEL} normal-case flex items-center gap-2`}>
                <Ban className="h-4 w-4 text-zinc-500" /> Coverage exclusion exposure
              </h3>
              <p className="text-[11px] text-zinc-500 mt-0.5 max-w-xl">Emerging exclusions carriers are adding to GL / umbrella / auto. "Mitigated" means you have the controls documented; "exposed" means address it before renewal.</p>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-bold text-red-400">{exclusions.summary.exposed} exposed</div>
              <div className="text-[10px] text-zinc-600">{exclusions.summary.total} relevant</div>
            </div>
          </div>
          <div className="space-y-2">
            {exclusions.exclusions.map((e) => (
              <div key={e.key} className="border-b border-white/[0.04] last:border-0 pb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-semibold uppercase w-16 shrink-0 ${EXCLUSION_TONE[e.status] ?? 'text-zinc-500'}`}>{e.status}</span>
                  <span className="text-sm text-zinc-200 flex-1">{e.label}</span>
                  <span className="text-[10px] text-zinc-600">{e.lines.join(' · ')}</span>
                </div>
                {e.status !== 'mitigated' && <p className="text-[11px] text-zinc-500 mt-0.5 ml-[4.5rem]">{e.mitigation}</p>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600 mt-2">Directional underwriting flag — which exclusions a risk like this typically faces, not a coverage determination.</p>
        </div>
      )}

      {/* How to improve — AI narrative (falls back to the static fixes) */}
      <div className={`${PANEL} p-5`}>
        <div className="flex items-center justify-between mb-3">
          <h3 className={LABEL}>How to improve your terms</h3>
          {!narrative && (
            <button onClick={explain} disabled={explaining} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-900/60 hover:border-emerald-700 disabled:opacity-50">
              {explaining ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} {explaining ? 'Thinking…' : 'Explain my risk'}
            </button>
          )}
        </div>
        {narrative ? (
          <div className="space-y-3">
            {narrative.summary && <p className="text-sm text-zinc-300 leading-relaxed">{narrative.summary}</p>}
            <ul className="space-y-2">
              {narrative.actions.map((a, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                  <ArrowUpRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" /><span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : data.top_fixes.length > 0 ? (
          <ul className="space-y-2">
            {data.top_fixes.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                <ArrowUpRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span className="capitalize">{f}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-zinc-500">You're in good shape — no priority fixes flagged.</p>
        )}
      </div>
    </div>
  )
}
