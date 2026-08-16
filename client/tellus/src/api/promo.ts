// Promo campaigns / QR reward cards — brand campaign+scanner CRUD, consumer
// card reads, and the public claim/scan surfaces. Mirrors the rest of
// api/tellusClient.ts's shape (no per-domain barrel elsewhere in this app).
import { tellusApi, tellusMaybeAuthGet, tellusPublicGet, tellusPublicPost } from './tellusClient'
import type {
  ClaimPreview,
  FlyerDesign,
  PromoCampaign,
  PromoCard,
  PromoClaimResult,
  PromoRedeemResult,
  PromoScanBootstrap,
  ScannerDevice,
  BoardPost,
} from './types'

export const promoApi = {
  listCampaigns: () => tellusApi.get<PromoCampaign[]>('/promo/campaigns'),
  createCampaign: (body: {
    title: string
    reward_text: string
    description?: string | null
    max_claims: number
    card_expiry_days?: number
    starts_at?: string | null
    ends_at?: string | null
    campaign_type?: 'qr' | 'location'
    store_id?: string | null
    radius_miles?: number | null
  }) => tellusApi.post<PromoCampaign>('/promo/campaigns', body),
  getCampaign: (id: string) => tellusApi.get<PromoCampaign>(`/promo/campaigns/${id}`),
  getDesign: (id: string) => tellusApi.get<{ design_json: FlyerDesign | null }>(`/promo/campaigns/${id}/design`),
  patchCampaign: (
    id: string,
    body: Partial<Pick<PromoCampaign, 'title' | 'reward_text' | 'description' | 'ends_at'>> & {
      status?: 'active' | 'paused'
    },
  ) => tellusApi.patch<PromoCampaign>(`/promo/campaigns/${id}`, body),
  cancelCampaign: (id: string) => tellusApi.post<{ invalidated_count: number }>(`/promo/campaigns/${id}/cancel`, {}),
  pushCampaign: (id: string) => tellusApi.post<{ sent_count: number; pushed: boolean; store_name: string; radius_miles: number }>(`/promo/campaigns/${id}/push`, {}),
  postToLocals: (campaign: Pick<PromoCampaign, 'id' | 'title' | 'description' | 'reward_text'>) =>
    tellusApi.post<BoardPost>('/board/posts', {
      kind: 'promo',
      title: campaign.title,
      body: campaign.description || campaign.reward_text,
      campaign_id: campaign.id,
    }),
  saveDesign: (id: string, design_json: FlyerDesign) =>
    tellusApi.put(`/promo/campaigns/${id}/design`, { design_json }),
  uploadFlyer: (id: string, form: FormData) =>
    tellusApi.upload<{ flyer_image_url: string }>(`/promo/campaigns/${id}/flyer`, form),

  listScanners: () => tellusApi.get<ScannerDevice[]>('/promo/scanners'),
  createScanner: (body: { store_id: string; label?: string }) =>
    tellusApi.post<ScannerDevice>('/promo/scanners', body),
  revokeScanner: (id: string) => tellusApi.post(`/promo/scanners/${id}/revoke`, {}),
  redeemAsBrand: (card_token: string) => tellusApi.post<PromoRedeemResult>('/promo/redeem', { card_token }),

  myCards: () => tellusApi.get<PromoCard[]>('/me/promo-cards'),
  myCard: (cardToken: string) => tellusApi.get<PromoCard>(`/me/promo-cards/${cardToken}`),

  // Public claim page — maybe-auth preview (liked_by_me-style already-claimed
  // detection when logged in), hard-auth claim (401 drives the login bounce).
  claimPreview: (token: string) => tellusMaybeAuthGet<ClaimPreview>(`/p/${token}`),
  claim: (token: string) => tellusApi.post<PromoClaimResult>(`/p/${token}/claim`, {}),

  // Public scanner page — device token IS the auth, no bearer involved.
  scanBootstrap: (deviceToken: string) => tellusPublicGet<PromoScanBootstrap>(`/scan/${deviceToken}`),
  scanRedeem: (deviceToken: string, card_token: string) =>
    tellusPublicPost<PromoRedeemResult>(`/scan/${deviceToken}/redeem`, { card_token }),
}
