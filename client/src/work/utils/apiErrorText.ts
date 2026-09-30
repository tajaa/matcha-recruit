import { ApiError } from '../../api/client'

/** What the server said went wrong, as one line for the person. FastAPI puts
 *  it in `detail`, either as a string or as `{ message }`. */
export function apiErrorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const body = error.body
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string' && detail) return detail
      if (detail && typeof detail === 'object' && 'message' in detail) {
        const text = (detail as { message: unknown }).message
        if (typeof text === 'string' && text) return text
      }
    }
  }
  return fallback
}
