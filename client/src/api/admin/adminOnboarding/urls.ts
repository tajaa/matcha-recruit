/**
 * Stream paths for the onboarding wizard. These answer with SSE, not JSON — the
 * stream IS the work (the server projects as it yields), so callers drive them
 * through `postSSE` (api/sse.ts) rather than `api.post`, which would choke
 * parsing `data: {...}`.
 *
 * Paths, not absolute URLs: postSSE prepends the API base itself.
 */

/** SSE enrichment stream — enriches a company from its roster. */
export function getEnrichStreamPath(companyId: string): string {
  return `/admin/onboarding/enrich/${companyId}/stream`
}

/** SSE selective gap-fill — researches only the chosen (jurisdiction, category)
 *  items. POSTed with a JSON body. */
export function getResearchGapsPath(companyId: string): string {
  return `/admin/onboarding/research-gaps/${companyId}/stream`
}

/** Per-location compliance re-check, scoped to a company (admin view). */
export function getLocationCheckPath(locationId: string, companyId: string): string {
  return `/compliance/locations/${locationId}/check?company_id=${companyId}`
}
