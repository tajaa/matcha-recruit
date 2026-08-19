import { tellusApi, tellusPublicGet, tellusPublicPost } from './tellusClient'
import type {
  LoyaltyEarnResult,
  LoyaltyLedgerEntry,
  LoyaltyMemberQr,
  LoyaltyProgram,
  LoyaltyProgramSummary,
  LoyaltyRedemption,
  LoyaltyRedeemResult,
  LoyaltyReward,
  LoyaltySocialSubmission,
} from './types'

export const loyaltyApi = {
  listPrograms: () => tellusApi.get<LoyaltyProgramSummary[]>('/me/loyalty/programs'),
  getProgram: (brandId: string) => tellusApi.get<LoyaltyProgram>(`/me/loyalty/programs/${brandId}`),
  mintMemberQr: (brandId: string) => tellusApi.post<LoyaltyMemberQr>(`/me/loyalty/programs/${brandId}/member-qr`, {}),
  listLedger: (brandId: string, limit = 50, offset = 0) =>
    tellusApi.get<LoyaltyLedgerEntry[]>(`/me/loyalty/programs/${brandId}/ledger?limit=${limit}&offset=${offset}`),
  issueRedemption: (brandId: string, rewardId: string, clientRequestId: string) =>
    tellusApi.post<LoyaltyRedemption>(`/me/loyalty/programs/${brandId}/redemptions`, {
      reward_id: rewardId,
      client_request_id: clientRequestId,
    }),
  listRedemptions: () => tellusApi.get<LoyaltyRedemption[]>('/me/loyalty/redemptions'),
  submitSocial: (brandId: string, body: { platform: string; post_url: string; note?: string | null }) =>
    tellusApi.post<LoyaltySocialSubmission>(`/me/loyalty/programs/${brandId}/social-submissions`, body),
  listMySocial: (brandId: string) =>
    tellusApi.get<LoyaltySocialSubmission[]>(`/me/loyalty/programs/${brandId}/social-submissions`),
  withdrawSocial: (id: string) => tellusApi.delete<void>(`/me/loyalty/social-submissions/${id}`),

  getBuilder: (brandId: string) => tellusApi.get<LoyaltyProgram>(`/businesses/${brandId}/loyalty/program`),
  saveBuilder: (brandId: string, body: unknown) =>
    tellusApi.put<LoyaltyProgram>(`/businesses/${brandId}/loyalty/program`, body),
  listRewards: (brandId: string) => tellusApi.get<LoyaltyReward[]>(`/businesses/${brandId}/loyalty/rewards`),
  createReward: (brandId: string, body: unknown) =>
    tellusApi.post<LoyaltyReward>(`/businesses/${brandId}/loyalty/rewards`, body),
  patchReward: (brandId: string, rewardId: string, body: unknown) =>
    tellusApi.patch<LoyaltyReward>(`/businesses/${brandId}/loyalty/rewards/${rewardId}`, body),
  listSocialQueue: (brandId: string) =>
    tellusApi.get<LoyaltySocialSubmission[]>(`/businesses/${brandId}/loyalty/social-submissions`),
  approveSocial: (brandId: string, id: string, note?: string) =>
    tellusApi.post<LoyaltySocialSubmission>(`/businesses/${brandId}/loyalty/social-submissions/${id}/approve`, { note }),
  rejectSocial: (brandId: string, id: string, note?: string) =>
    tellusApi.post<LoyaltySocialSubmission>(`/businesses/${brandId}/loyalty/social-submissions/${id}/reject`, { note }),
  summary: (brandId: string) => tellusApi.get<Record<string, number>>(`/businesses/${brandId}/loyalty/summary`),

  purchase: (brandId: string, storeId: string, memberToken: string, amountCents: number) =>
    tellusApi.post<LoyaltyEarnResult>(`/businesses/${brandId}/stores/${storeId}/loyalty/purchase`, {
      member_token: memberToken,
      amount_cents: amountCents,
    }),
  redeem: (brandId: string, storeId: string, redemptionToken: string) =>
    tellusApi.post<LoyaltyRedeemResult>(`/businesses/${brandId}/stores/${storeId}/loyalty/redemptions/redeem`, {
      redemption_token: redemptionToken,
    }),
  scannerVisit: (deviceToken: string, memberToken: string) =>
    tellusPublicPost<LoyaltyEarnResult>(`/scan/${deviceToken}/loyalty/visit`, { member_token: memberToken }),
  publicProgram: (slug: string) => tellusPublicGet<LoyaltyProgram>(`/b/${slug}/loyalty`),
}
