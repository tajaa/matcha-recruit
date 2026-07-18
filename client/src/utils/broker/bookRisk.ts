// Client-side exposure-weighted book-risk math for the broker Risk Curve.
//
// computeWeightedBookRisk is an exact port of the canonical Python helper
// app.matcha.services.risk_index.weighted_book_risk — keep the two in sync (the
// vitest suite ports the same fixtures as the pytest to guard against drift).

import type { BookRiskClient, ExposureBasis, WeightedBookRisk } from '../../types/riskIndex'

const BANDS = ['strong', 'adequate', 'developing', 'exposed'] as const
const CONFIDENCES = ['high', 'moderate', 'low'] as const

const round1 = (n: number) => Math.round(n * 10) / 10
const round2 = (n: number) => Math.round(n * 100) / 100
const round4 = (n: number) => Math.round(n * 10000) / 10000

// mirror epl_readiness.readiness_band
export function bandOf(score: number): string {
  if (score >= 80) return 'strong'
  if (score >= 60) return 'adequate'
  if (score >= 35) return 'developing'
  return 'exposed'
}

export function weightField(basis: ExposureBasis): 'headcount' | 'annual_premium' {
  return basis === 'premium' ? 'annual_premium' : 'headcount'
}

export function weightOf(c: BookRiskClient, basis: ExposureBasis): number {
  const v = c[weightField(basis)]
  return v && v > 0 ? v : 0
}

export function computeWeightedBookRisk(clients: BookRiskClient[], basis: ExposureBasis): WeightedBookRisk {
  const scored = clients.filter((c) => c.index != null)
  const weights = scored.map((c) => weightOf(c, basis))
  const totalWeight = weights.reduce((a, b) => a + b, 0)

  const weightedMean = totalWeight > 0
    ? round1(scored.reduce((s, c, i) => s + c.index * weights[i], 0) / totalWeight)
    : null
  const equalWeightMean = scored.length
    ? round1(scored.reduce((s, c) => s + c.index, 0) / scored.length)
    : null

  const bandMix: Record<string, number> = { strong: 0, adequate: 0, developing: 0, exposed: 0 }
  const confidenceMix: Record<string, number> = { high: 0, moderate: 0, low: 0 }
  if (totalWeight > 0) {
    scored.forEach((c, i) => {
      if (c.band in bandMix) bandMix[c.band] += weights[i] / totalWeight
      if (c.confidence && c.confidence in confidenceMix) confidenceMix[c.confidence] += weights[i] / totalWeight
    })
    for (const b of BANDS) bandMix[b] = round4(bandMix[b])
    for (const conf of CONFIDENCES) confidenceMix[conf] = round4(confidenceMix[conf])
  }

  return {
    basis,
    weighted_mean: weightedMean,
    equal_weight_mean: equalWeightMean,
    weighted_band: weightedMean != null ? bandOf(Math.round(weightedMean)) : null,
    total_weight: round2(totalWeight),
    scored_count: scored.length,
    weighted_count: weights.filter((w) => w > 0).length,
    missing_basis_count: weights.filter((w) => w <= 0).length,
    band_mix: bandMix,
    confidence_mix: confidenceMix,
  }
}

// --- Aggregate loss distribution (the actual "risk curve") ------------------
//
// Models the book's annual loss as a log-normal — the standard actuarial shape for
// aggregate loss (right-skewed, fat right tail). Per client: expected loss ≈
// exposure × loss ratio; volatility (coefficient of variation) scales with the
// client's risk index, so an exposed client fattens the tail far more than a strong
// one. The book sums independent client losses (mean + variance add); we fit a
// log-normal to those two moments (Fenton–Wilkinson) — deterministic, no simulation.
//
// Directional, not a priced actuarial estimate: we don't have a true
// frequency/severity model, so exposure stands in for expected loss.

const LOSS_RATIO = 0.65          // permissible loss ratio: expected loss ≈ premium × this
const PREMIUM_PER_HEAD = 1200    // headcount-basis assumption (~$/employee WC premium)
const Z95 = 1.645
const Z99 = 2.326

// risk index 100 (strong) → low CoV 0.4; index 0 (exposed) → high CoV 2.0.
function covOf(index: number): number {
  return Math.min(2.0, Math.max(0.4, 0.4 + 1.6 * (100 - index) / 100))
}

function exposureOf(c: BookRiskClient, basis: ExposureBasis): number | null {
  if (basis === 'premium') return c.annual_premium && c.annual_premium > 0 ? c.annual_premium : null
  return c.headcount && c.headcount > 0 ? c.headcount * PREMIUM_PER_HEAD : null
}

// standard-normal CDF (Abramowitz & Stegun 26.2.17) — for the exceedance read.
function normCdf(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z))
  const d = 0.3989423 * Math.exp(-z * z / 2)
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
  return z > 0 ? 1 - p : p
}

export interface BookLoss {
  basis: ExposureBasis
  expected_loss: number          // M = Σ expected client loss
  std: number                    // √(Σ variance)
  pml95: number                  // 95th-pct annual loss
  pml99: number                  // 99th-pct annual loss (1-in-100 tail)
  mu: number | null              // log-normal params (null when no exposure to model)
  sigma: number | null
  modeled_count: number
  missing_exposure_count: number
}

export function computeBookLoss(clients: BookRiskClient[], basis: ExposureBasis): BookLoss {
  const scored = clients.filter((c) => c.index != null)
  let M = 0, V = 0, modeled = 0, missing = 0
  for (const c of scored) {
    const E = exposureOf(c, basis)
    if (E == null) { missing++; continue }
    const muI = E * LOSS_RATIO
    V += Math.pow(covOf(c.index) * muI, 2)
    M += muI
    modeled++
  }
  if (M <= 0) {
    return { basis, expected_loss: 0, std: 0, pml95: 0, pml99: 0, mu: null, sigma: null,
      modeled_count: modeled, missing_exposure_count: missing }
  }
  const sigma2 = Math.log(1 + V / (M * M))
  const sigma = Math.sqrt(sigma2)
  const mu = Math.log(M) - sigma2 / 2
  return {
    basis,
    expected_loss: Math.round(M),
    std: Math.round(Math.sqrt(V)),
    pml95: Math.round(Math.exp(mu + Z95 * sigma)),
    pml99: Math.round(Math.exp(mu + Z99 * sigma)),
    mu, sigma,
    modeled_count: modeled,
    missing_exposure_count: missing,
  }
}

export interface LossPoint {
  x: number          // annual loss $
  density: number    // peak-normalized likelihood (0–1, for the curve shape)
  exceed: number     // P(annual book loss ≥ x)
}

// The log-normal loss PDF sampled across the loss axis (peak-normalized for display)
// plus the exceedance probability at each point (the underwriter read).
export function buildLossCurve(clients: BookRiskClient[], basis: ExposureBasis, opts: { points?: number } = {}): LossPoint[] {
  const L = computeBookLoss(clients, basis)
  if (L.mu == null || L.sigma == null || L.expected_loss <= 0) return []
  const { mu, sigma } = L
  const n = opts.points ?? 90
  const xmax = Math.max(L.pml99 * 1.2, L.expected_loss * 2.2)
  const dx = xmax / n
  const pts: LossPoint[] = []
  let peak = 0
  for (let i = 1; i <= n; i++) {
    const x = dx * i
    const lx = Math.log(x)
    const pdf = (1 / (x * sigma * Math.sqrt(2 * Math.PI))) * Math.exp(-Math.pow(lx - mu, 2) / (2 * sigma * sigma))
    pts.push({ x: Math.round(x), density: pdf, exceed: 1 - normCdf((lx - mu) / sigma) })
    if (pdf > peak) peak = pdf
  }
  return peak > 0 ? pts.map((p) => ({ ...p, density: round4(p.density / peak) })) : pts
}
