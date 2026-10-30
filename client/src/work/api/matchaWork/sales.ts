import { api } from '../../../api/client'

// Espresso Sales campaigns (`/matcha-work/sales`), the same API the macOS
// Pipeline uses. A campaign lives in a collab workspace and is private to the
// person who made it. Nothing here sends on its own: a batch goes out only
// after the person approves exactly what they reviewed (`sendBatch`), and the
// server checks each message's `review_token` against what is stored.

export type SalesPlaybook = '' | 'consulting'
export type SalesSegment = '' | 'growing' | 'regulated' | 'ai' | 'hourly'
export type SalesService = '' | 'hr' | 'grc' | 'er' | 'ai'
export type SalesStage = 'lead' | 'qualified' | 'proposal' | 'negotiation' | 'closed'
export type ProspectStatus =
  | 'prospect' | 'draft' | 'approved' | 'claimed' | 'sent' | 'failed' | 'unknown' | 'opted_out'
export type CampaignStatus = 'idle' | 'sending' | 'paused' | 'complete'

export interface SalesWorkspace {
  id: string
  title: string
}

export interface SalesCampaign {
  id: string
  project_id: string
  title: string
  target: string
  offer: string
  footer: string
  playbook: SalesPlaybook
  cta_url: string
  status: CampaignStatus
  sender: string | null
  error: string | null
  updated_at: string
}

export interface WorkspaceCampaign {
  id: string
  title: string
  status: CampaignStatus
  creator: string
  prospects: number
  sent: number
  problems: number
}

export interface SalesProspect {
  id: string
  email: string
  name: string
  company: string
  website: string
  notes: string
  research: string
  sources: string[]
  subject: string
  body: string
  stage: SalesStage
  status: ProspectStatus
  error: string | null
  sent_at: string | null
  segment: SalesSegment
  service: SalesService
  signal: string
  fit: number | null
  review_token: string
  /** Consulting campaigns: what the draft checks found (empty when it passes). */
  review_flags?: string[]
}

export interface PlaybookGuide {
  key: SalesPlaybook
  label: string
  segments: { key: SalesSegment; label: string; buyer: string; service: SalesService; signals: string[] }[]
  services: { key: SalesService; label: string }[]
  max_words: number
}

export interface SalesCampaignDetail {
  campaign: SalesCampaign
  prospects: SalesProspect[]
  counts: Partial<Record<ProspectStatus, number>>
  offset: number
  playbook?: PlaybookGuide
}

export interface SalesStatus {
  campaign: SalesCampaign
  counts: Partial<Record<ProspectStatus, number>>
  prospects: { id: string; status: ProspectStatus; error: string | null; review_token: string }[]
}

export interface HouseOffer {
  title: string
  target: string
  offer: string
  cta_url: string
  playbook: SalesPlaybook
}

export interface PlaybookOptions {
  playbooks: PlaybookGuide[]
  /** Matcha's own consulting offer: Matcha staff only, otherwise null. */
  house: HouseOffer | null
}

export interface ContactInput {
  email: string
  name: string
  company: string
  website: string
  notes: string
}

export interface CampaignInput {
  title: string
  target?: string
  offer?: string
  footer?: string
  playbook?: SalesPlaybook
  cta_url?: string
  house?: boolean
}

export type CampaignChanges = Partial<Pick<SalesCampaign, 'title' | 'target' | 'offer' | 'footer' | 'playbook' | 'cta_url'>>

export type ProspectChanges = Partial<Pick<SalesProspect,
  'stage' | 'subject' | 'body' | 'email' | 'segment' | 'service' | 'signal'>> & {
  fit?: number
  /** The version the person opened: a newer draft (Espresso's) refuses the save. */
  review_token?: string
}

export type CampaignAction = 'pause' | 'resume' | 'release_pending' | 'retry_failed'

const base = '/matcha-work'

export const listSalesWorkspaces = () =>
  api.get<{ workspaces: SalesWorkspace[] }>(`${base}/sales/workspaces`)

export const getPlaybookOptions = () => api.get<PlaybookOptions>(`${base}/sales/playbooks`)

export const listCampaigns = (projectId: string) =>
  api.get<{ campaigns: SalesCampaign[]; workspace_campaigns: WorkspaceCampaign[] }>(
    `${base}/projects/${projectId}/sales`,
  )

export const createCampaign = (projectId: string, body: CampaignInput) =>
  api.post<SalesCampaign>(`${base}/projects/${projectId}/sales`, { request_id: crypto.randomUUID(), ...body })

export const getCampaign = (campaignId: string) =>
  api.get<SalesCampaignDetail>(`${base}/sales/${campaignId}`)

export const getCampaignStatus = (campaignId: string) =>
  api.get<SalesStatus>(`${base}/sales/${campaignId}/status`)

export const updateCampaign = (campaignId: string, changes: CampaignChanges) =>
  api.patch<SalesCampaign>(`${base}/sales/${campaignId}`, changes)

export const deleteCampaign = (campaignId: string) =>
  api.delete<{ deleted: boolean }>(`${base}/sales/${campaignId}`)

export const importProspects = (campaignId: string, prospects: ContactInput[]) =>
  api.post<{ added: number; duplicates: number; suppressed: number }>(
    `${base}/sales/${campaignId}/prospects`, { prospects },
  )

export const updateProspect = (campaignId: string, prospectId: string, changes: ProspectChanges) =>
  api.patch<SalesProspect>(`${base}/sales/${campaignId}/prospects/${prospectId}`, changes)

export const deleteProspect = (campaignId: string, prospectId: string) =>
  api.delete<{ deleted: boolean }>(`${base}/sales/${campaignId}/prospects/${prospectId}`)

export const optOutProspect = (campaignId: string, prospectId: string) =>
  api.post<SalesProspect>(`${base}/sales/${campaignId}/prospects/${prospectId}/opt-out`)

export const resolveUnknown = (campaignId: string, prospectId: string, outcome: 'sent' | 'not_sent') =>
  api.post<SalesProspect>(`${base}/sales/${campaignId}/prospects/${prospectId}/resolve`, { outcome })

export const sendBatch = (
  campaignId: string,
  sender: string,
  drafts: { id: string; review_token: string }[],
  requestId: string,
) => api.post<{ status: string }>(`${base}/sales/${campaignId}/send`, { request_id: requestId, sender, drafts })

export const campaignAction = (campaignId: string, action: CampaignAction) =>
  api.post<{ status: string }>(`${base}/sales/${campaignId}/action`, { action })
