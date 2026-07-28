import { api, API_BASE, authStreamHeaders } from '../../api/client'
import type { OfferLetterDetail } from '../types'

/** Structured offer-letter fields (candidate/position/salary/status/…) —
 * not the rendered letter body. */
export function getOfferLetter(offerId: string): Promise<OfferLetterDetail> {
  return api.get<OfferLetterDetail>(`/offer-letters/${offerId}`)
}

/** The rendered letter itself — same HTML the PDF and candidate signing page
 * produce (`GET /offer-letters/{id}/preview`). Plain fetch + authStreamHeaders
 * rather than the `api` helper since the response is text/html, not JSON. */
export async function getOfferLetterPreviewHtml(offerId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/offer-letters/${offerId}/preview`, {
    headers: await authStreamHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load offer preview (${res.status})`)
  return res.text()
}
