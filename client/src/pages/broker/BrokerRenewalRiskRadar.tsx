import { useEffect, useMemo, useState } from 'react'
import {
  Radar,
  Loader2,
  AlertCircle,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
  Building2,
  MapPin,
  Download,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react'
import { StatCard } from '../../components/dashboard'
import { Button, Badge, Modal, useToast } from '../../components/ui'
import type { BadgeVariant } from '../../components/ui'
import { fetchRenewalRadar, fetchRenewalRadarDetail, downloadStabilizationKit } from '../../api/broker'
import TabHeader from '../../components/broker/action-center/TabHeader'
import type {
  RenewalRadarCompany,
  RenewalRadarSummary,
  RenewalRadarDetail,
  RenewalRiskBand,
  RenewalRiskDimension,
} from '../../types/broker'

const BAND_RANK: Record<RenewalRiskBand, number> = { critical: 0, elevated: 1, stable: 2 }

const BAND_VARIANT: Record<RenewalRiskBand, BadgeVariant> = {
  critical: 'danger',
  elevated: 'warning',
  stable: 'success',
}

const BAND_LABEL: Record<RenewalRiskBand, string> = {
  critical: 'Critical',
  elevated: 'Elevated',
  stable: 'Stable',
}

const BAND_ACCENT: Record<RenewalRiskBand, string> = {
  critical: 'border-l-red-500',
  elevated: 'border-l-amber-500',
  stable: 'border-l-emerald-500',
}

const EMPTY_SUMMARY: RenewalRadarSummary = {
  client_count: 0,
  stable: 0,
  elevated: 0,
  critical: 0,
}

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`
}

function fmtMoney(n: number | null): string {
  if (n == null) return '—'
  return `$${Math.round(n).toLocaleString()}`
}

function policyMonthLabel(month: number | null): string | null {
  if (month == null) return null
  return `Month ${month} of policy`
}

// Delta indicator: positive turnover delta = worse (more turnover), shown red.
function Delta({ value, invert = false }: { value: number; invert?: boolean }) {
  if (value === 0) return <span className="text-zinc-500 text-xs">flat</span>
  const worse = invert ? value < 0 : value > 0
  const Icon = value > 0 ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs ${worse ? 'text-red-400' : 'text-emerald-400'}`}>
      <Icon size={11} />
      {value > 0 ? '+' : ''}
      {value.toFixed(1)}%
    </span>
  )
}

// --- Deep-dive modal ---

function DimensionCard({ dim }: { dim: RenewalRiskDimension }) {
  const Icon = dim.dimension_type === 'location' ? MapPin : Building2
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-zinc-100 flex items-center gap-1.5">
          <Icon size={13} className="text-zinc-500" />
          {dim.dimension_value}
          <span className="text-[10px] uppercase tracking-wider text-zinc-600">{dim.dimension_type}</span>
        </p>
        <Badge variant={BAND_VARIANT[dim.risk_band]}>{BAND_LABEL[dim.risk_band]}</Badge>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-xs">
        <div>
          <p className="text-zinc-500">Turnover</p>
          <p className="text-zinc-200 mt-0.5 flex items-center gap-1.5">
            {fmtPct(dim.turnover_pct)} <Delta value={dim.turnover_delta_pct} />
          </p>
          <p className="text-[10px] text-zinc-600">base {fmtPct(dim.turnover_baseline_pct)}</p>
        </div>
        <div>
          <p className="text-zinc-500">Lost workdays</p>
          <p className="text-zinc-200 mt-0.5 flex items-center gap-1.5">
            {dim.lost_workdays} <Delta value={dim.lost_workdays_delta_pct} />
          </p>
        </div>
        <div>
          <p className="text-zinc-500">Near misses</p>
          <p className="text-zinc-200 mt-0.5">{dim.near_misses}</p>
        </div>
        <div>
          <p className="text-zinc-500">Headcount</p>
          <p className="text-zinc-200 mt-0.5">{dim.headcount}</p>
        </div>
      </div>

      {dim.behavioral_incidents > 0 && (
        <p className="text-[11px] text-zinc-500 mt-2">
          {dim.behavioral_incidents} behavioral incident{dim.behavioral_incidents !== 1 ? 's' : ''} ·{' '}
          gross payroll {fmtMoney(dim.gross_payroll)}
        </p>
      )}

      {dim.triggers.length > 0 && (
        <ul className="mt-3 space-y-1">
          {dim.triggers.map((t, i) => (
            <li key={i} className="text-xs text-amber-300/90 flex items-start gap-1.5">
              <span className="mt-1 h-1 w-1 rounded-full bg-amber-400 shrink-0" />
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DeepDiveModal({
  company,
  onClose,
}: {
  company: RenewalRadarCompany
  onClose: () => void
}) {
  const { toast } = useToast()
  const [detail, setDetail] = useState<RenewalRadarDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    fetchRenewalRadarDetail(company.company_id)
      .then((res) => {
        if (active) setDetail(res)
      })
      .catch(() => {
        if (active) setError('Failed to load risk detail.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [company.company_id])

  async function handleDownload() {
    setDownloading(true)
    try {
      await downloadStabilizationKit(company.company_id)
    } catch {
      toast('Failed to download kit', 'error')
    } finally {
      setDownloading(false)
    }
  }

  const month = detail?.policy_month ?? company.policy_month
  const monthSuffix = month != null ? ` (Month ${month} of Policy)` : ''

  return (
    <Modal open onClose={onClose} title={company.company_name} width="xl">
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Badge variant={BAND_VARIANT[company.risk_band]}>{BAND_LABEL[company.risk_band]}</Badge>
          <p className="text-sm font-medium text-zinc-200">
            Renewal Exposure Trend Warning{monthSuffix}
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-zinc-500">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-zinc-500">
            <AlertCircle className="h-8 w-8 mb-2 text-red-400" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        ) : detail ? (
          <>
            <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
              {detail.dimensions.map((dim, i) => (
                <DimensionCard key={`${dim.dimension_type}-${dim.dimension_value}-${i}`} dim={dim} />
              ))}
            </div>

            {detail.recommendation && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
                <p className="text-[10px] uppercase tracking-wider text-emerald-400/80 font-semibold mb-1 flex items-center gap-1.5">
                  <ShieldCheck size={12} />
                  Recommendation
                </p>
                <p className="text-sm text-zinc-200 leading-relaxed">{detail.recommendation}</p>
              </div>
            )}

            <div className="flex items-center justify-between gap-2 pt-2 border-t border-zinc-800">
              <Button size="sm" disabled={downloading} onClick={handleDownload}>
                {downloading ? (
                  <Loader2 size={14} className="mr-1 animate-spin" />
                ) : (
                  <Download size={14} className="mr-1" />
                )}
                Download Workforce Stabilization Kit
              </Button>
              <Button size="sm" variant="ghost" onClick={onClose}>
                Close
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </Modal>
  )
}

export default function BrokerRenewalRiskRadar() {
  const [companies, setCompanies] = useState<RenewalRadarCompany[]>([])
  const [summary, setSummary] = useState<RenewalRadarSummary>(EMPTY_SUMMARY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<RenewalRadarCompany | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchRenewalRadar()
      .then((res) => {
        setCompanies(res.companies)
        setSummary(res.summary)
      })
      .catch(() => setError('Failed to load renewal radar.'))
      .finally(() => setLoading(false))
  }, [])

  const sorted = useMemo(
    () => [...companies].sort((a, b) => BAND_RANK[a.risk_band] - BAND_RANK[b.risk_band]),
    [companies],
  )

  return (
    <div className="space-y-4">
      <TabHeader
        icon={Radar}
        title="Renewal Risk Radar"
        hint="Workforce signals that predict premium exposure at renewal. Open a client to see the drivers."
      />

      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Stable" value={summary.stable} icon={CheckCircle2} />
        <StatCard
          label="Elevated"
          value={summary.elevated}
          icon={TrendingUp}
          urgent={summary.elevated > 0}
        />
        <StatCard
          label="Critical Exposure"
          value={summary.critical}
          icon={AlertCircle}
          urgent={summary.critical > 0}
        />
      </div>

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-zinc-500">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <AlertCircle className="h-8 w-8 mb-2 text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500 border border-zinc-800 rounded-xl border-dashed">
          <CheckCircle2 className="h-10 w-10 text-emerald-500/60 mb-3" />
          <p className="text-sm font-medium text-zinc-400">No clients on the radar yet</p>
          <p className="text-xs mt-1">Workforce risk signals will appear here as data accrues.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((c) => {
            const month = policyMonthLabel(c.policy_month)
            return (
              <button
                key={c.company_id}
                type="button"
                onClick={() => setSelected(c)}
                className={`w-full text-left rounded-xl border border-zinc-800 border-l-4 ${BAND_ACCENT[c.risk_band]} bg-zinc-900/60 p-4 hover:bg-zinc-800/60 transition-colors`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-zinc-100 truncate">{c.company_name}</p>
                      <Badge variant={BAND_VARIANT[c.risk_band]}>{BAND_LABEL[c.risk_band]}</Badge>
                    </div>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      {c.industry || 'Unknown industry'}
                      {month ? ` · ${month}` : ''} · {c.headcount} employees
                    </p>
                    {c.top_trigger && (
                      <p className="text-xs text-amber-300/90 mt-1.5 flex items-center gap-1.5">
                        <span className="h-1 w-1 rounded-full bg-amber-400 shrink-0" />
                        {c.top_trigger}
                      </p>
                    )}
                  </div>
                  <ChevronRight className="h-4 w-4 text-zinc-600 shrink-0" />
                </div>

                <div className="grid grid-cols-3 gap-3 mt-3 pt-3 border-t border-zinc-800 text-xs">
                  <div>
                    <p className="text-zinc-500">Turnover</p>
                    <p className="text-zinc-200 mt-0.5 flex items-center gap-1.5">
                      {fmtPct(c.turnover_pct)} <Delta value={c.turnover_delta_pct} />
                    </p>
                  </div>
                  <div>
                    <p className="text-zinc-500">Lost workdays</p>
                    <p className="text-zinc-200 mt-0.5">{c.lost_workdays}</p>
                  </div>
                  <div>
                    <p className="text-zinc-500">Near misses</p>
                    <p className="text-zinc-200 mt-0.5">{c.near_misses}</p>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      )}

      {selected && <DeepDiveModal company={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
