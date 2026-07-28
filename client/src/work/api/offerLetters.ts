import { api } from '../../api/client'
import type { OfferLetterDetail } from '../types'

/** Structured offer-letter fields (candidate/position/salary/status/…) —
 * not the rendered letter body. */
export function getOfferLetter(offerId: string): Promise<OfferLetterDetail> {
  return api.get<OfferLetterDetail>(`/offer-letters/${offerId}`)
}

/** The rendered letter itself — same HTML the PDF and candidate signing page
 * produce (`GET /offer-letters/{id}/preview`). Uses `api.getText` (not the
 * plain `api` JSON helpers, since the response is text/html) — it's a
 * single, replayable response, so it gets the same proactive-refresh +
 * one-shot 401-retry as everything else, unlike an SSE/WS stream. */
export function getOfferLetterPreviewHtml(offerId: string): Promise<string> {
  return api.getText(`/offer-letters/${offerId}/preview`)
}
