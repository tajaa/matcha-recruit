// Shared base URL for matcha-work streaming (SSE) calls that use raw `fetch`
// instead of the `api` helper. Kept internal to the matchaWork package.

export const BASE = import.meta.env.VITE_API_URL ?? '/api'
