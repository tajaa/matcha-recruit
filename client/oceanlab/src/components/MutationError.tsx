interface ApiErrorResponse {
  response?: {
    data?: {
      detail?: unknown
    }
  }
  message?: string
}

function extractMessage(error: unknown): string {
  const err = error as ApiErrorResponse
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail != null) return JSON.stringify(detail)
  if (err?.message) return err.message
  return String(error)
}

export function MutationError({ error }: { error: unknown }) {
  if (!error) return null
  return <p className="text-xs text-red-600 mt-1">{extractMessage(error)}</p>
}
