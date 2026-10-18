/** Recaps live in Tasks, under its Recaps view. `recap` opens one; `source`
 *  narrows the list to one task's recaps. Older `/recaps` links (the
 *  completion email's among them) redirect here. */
export function recapsPath(base: string, { recap, source }: { recap?: string | null; source?: string | null } = {}) {
  const query = new URLSearchParams({ view: 'recaps' })
  if (recap) query.set('recap', recap)
  if (source) query.set('source_id', source)
  return `${base}/tasks?${query}`
}
