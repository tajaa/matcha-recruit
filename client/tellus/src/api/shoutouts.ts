import { tellusApi, tellusMaybeAuthGet } from './tellusClient'
import type {
  ShoutoutConfig,
  ShoutoutMention,
  ShoutoutOffer,
  ShoutoutOfferClaimResult,
  ShoutoutOfferPreview,
  ShoutoutRun,
  ShoutoutScanResult,
  ShoutoutPlatform,
  ShoutoutManualScan,
  ShoutoutStats,
  ShoutoutTestPost,
} from './types'

export const shoutoutApi = {
  getConfig: (brandId: string) => tellusApi.get<ShoutoutConfig>(`/businesses/${brandId}/shoutouts/config`),
  putConfig: (brandId: string, body: Omit<ShoutoutConfig, 'is_enabled' | 'platform_coverage' | 'last_scanned_at' | 'next_scan_after'>) =>
    tellusApi.put<ShoutoutConfig>(`/businesses/${brandId}/shoutouts/config`, body),
  setEnabled: (brandId: string, enabled: boolean) =>
    tellusApi.post<ShoutoutConfig>(`/businesses/${brandId}/shoutouts/config/enable`, { enabled }),
  listMentions: (brandId: string, status = 'pending') =>
    tellusApi.get<ShoutoutMention[]>(`/businesses/${brandId}/shoutouts/mentions?status=${status}`),
  approve: (brandId: string, mentionId: string, body: {
    store_id?: string | null
    title?: string | null
    terms?: string | null
    expiry_days?: number | null
  }) =>
    tellusApi.post<ShoutoutOffer>(`/businesses/${brandId}/shoutouts/mentions/${mentionId}/approve`, {
      client_request_id: crypto.randomUUID(),
      ...body,
    }),
  fetchStats: (brandId: string, mentionId: string) =>
    tellusApi.post<ShoutoutStats>(`/businesses/${brandId}/shoutouts/mentions/${mentionId}/stats`, {}),
  reject: (brandId: string, mentionId: string, note?: string) =>
    tellusApi.post<void>(`/businesses/${brandId}/shoutouts/mentions/${mentionId}/reject`, { note }),
  listOffers: (brandId: string) => tellusApi.get<ShoutoutOffer[]>(`/businesses/${brandId}/shoutouts/offers`),
  revokeOffer: (brandId: string, offerId: string, note?: string) =>
    tellusApi.post<void>(`/businesses/${brandId}/shoutouts/offers/${offerId}/revoke`, { note }),
  listRuns: (brandId: string) => tellusApi.get<ShoutoutRun[]>(`/businesses/${brandId}/shoutouts/runs`),
  runManualScan: (brandId: string, body: ShoutoutManualScan) => tellusApi.post<ShoutoutScanResult>(`/businesses/${brandId}/shoutouts/scan`, body),
  submitTestPost: (brandId: string, body: ShoutoutTestPost) =>
    tellusApi.post(`/businesses/${brandId}/shoutouts/test-posts`, body),
  socialSubmissions: (brandId: string) => tellusApi.get<import('./types').LoyaltySocialSubmission[]>(`/businesses/${brandId}/loyalty/social-submissions`),
  decideSocial: (brandId: string, submissionId: string, decision: 'approve' | 'reject', note?: string) =>
    tellusApi.post(`/businesses/${brandId}/loyalty/social-submissions/${submissionId}/${decision}`, { note }),
  previewOffer: (token: string) => tellusMaybeAuthGet<ShoutoutOfferPreview>(`/o/${token}`),
  previewCode: (code: string) => tellusMaybeAuthGet<ShoutoutOfferPreview>(`/o/code/${code}`),
  claimOffer: (token: string) => tellusApi.post<ShoutoutOfferClaimResult>(`/o/${token}/claim`, {}),
  claimCode: (code: string) => tellusApi.post<ShoutoutOfferClaimResult>(`/o/code/${code}/claim`, {}),
}

export type { ShoutoutPlatform }
