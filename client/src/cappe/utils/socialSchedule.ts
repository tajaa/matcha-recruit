// Pure helpers for the Social composer: datetime-local <-> ISO, the default
// first slot, spreading a batch of photos across days, and hashtags.

const pad = (n: number) => String(n).padStart(2, '0')

/** A Date as the value a datetime-local input shows (local time, minutes). */
export function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** A datetime-local value, read as the browser's local time, as ISO (UTC).
 *  Null for an empty or unreadable value. */
export function localInputToIso(value: string): string | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Why a datetime-local value can't be a schedule time, or null. */
export function scheduleError(value: string, now: Date = new Date()): string | null {
  const iso = localInputToIso(value)
  if (!iso) return 'Pick a time'
  return new Date(iso).getTime() < now.getTime() ? 'Pick a time in the future' : null
}

/** The default first slot: the next whole hour at least 15 minutes away. */
export function nextSlot(now: Date = new Date()): Date {
  const d = new Date(now.getTime() + 15 * 60_000)
  if (d.getMinutes() || d.getSeconds() || d.getMilliseconds()) {
    d.setHours(d.getHours() + 1, 0, 0, 0)
  }
  return d
}

/** `count` times from `start`, `everyDays` apart, at the same wall-clock time
 *  (setDate keeps the local hour across a daylight-saving change). */
export function spreadTimes(start: Date, count: number, everyDays: number): Date[] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => {
    const d = new Date(start.getTime())
    d.setDate(d.getDate() + i * Math.max(1, everyDays))
    return d
  })
}

/** `#word` per tag (letters, digits, underscore), lowercased, de-duplicated. */
export function normalizeHashtags(raw: string | string[]): string[] {
  const parts = Array.isArray(raw) ? raw : raw.split(/[\s,]+/)
  const out: string[] = []
  for (const part of parts) {
    const word = part.trim().replace(/^#+/, '').replace(/[^\p{L}\p{N}_]/gu, '').toLowerCase()
    if (word && !out.includes(`#${word}`)) out.push(`#${word}`)
  }
  return out
}

/** The caption with `tags` appended on their own line, skipping any already
 *  in it. */
export function withHashtags(caption: string, tags: string[]): string {
  const present = new Set((caption.match(/#[\p{L}\p{N}_]+/gu) ?? []).map((t) => t.toLowerCase()))
  const missing = normalizeHashtags(tags).filter((t) => !present.has(t))
  if (!missing.length) return caption
  const base = caption.trimEnd()
  return base ? `${base}\n\n${missing.join(' ')}` : missing.join(' ')
}

/** Instagram's caption limit; the composer counts against it. */
export const CAPTION_LIMIT = 2200
