/**
 * Absolute stream URLs for the onboarding wizard — consumed via fetch +
 * ReadableStream (not EventSource) so the Authorization header can be attached.
 */

// Absolute URL for the SSE enrichment stream — consumed via fetch + ReadableStream
// (not EventSource) so the Authorization header can be attached. Mirrors
// getComplianceCheckUrl in api/compliance.ts.
export function getEnrichStreamUrl(companyId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/admin/onboarding/enrich/${companyId}/stream`
}

// SSE selective gap-fill — researches only the chosen (jurisdiction, category)
// items. POST with a JSON body, consumed via fetch + ReadableStream.
export function getResearchGapsUrl(companyId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/admin/onboarding/research-gaps/${companyId}/stream`
}

/** Per-location compliance re-check. Answers with SSE, not JSON — the stream IS
 *  the work (the server projects as it yields), so callers must fetch+drain it
 *  rather than go through `api.post`, which would choke parsing `data: {...}`. */
export function getLocationCheckUrl(locationId: string, companyId: string): string {
  const base = import.meta.env.VITE_API_URL || '/api'
  return `${base}/compliance/locations/${locationId}/check?company_id=${companyId}`
}
