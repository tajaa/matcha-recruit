// Scan previews remain opaque on the apply path; only the display fields are
// narrowed by the preview component before rendering them.
export type FederalSourcePreview = {
  results: unknown[]
  by_category: Record<string, unknown[]>
  total: number
}
