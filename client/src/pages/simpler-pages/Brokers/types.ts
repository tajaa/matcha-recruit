export type RiskBand = 'critical' | 'elevated' | 'stable'

export type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  highlight: string
  accent: string
}

export type RadarRow = {
  client: string
  band: RiskBand
  metric: string
  delta: string
  trir: string
  premiumDelta: string
}
