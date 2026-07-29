/** Detects the active `@`-token at the caret, e.g. for driving a mention
 * autocomplete dropdown. Pure — no coupling to channel members or any
 * particular @-target vocabulary (channel members, Huume, …); callers match
 * the returned query against whatever their own candidate list is. */
export function detectMentionToken(
  value: string,
  caret: number,
): { query: string; tokenStart: number } | null {
  // Look back from caret to find the active @-token. A token starts at @ and
  // is preceded by start-of-string or whitespace. Stops at first whitespace.
  let i = caret - 1
  while (i >= 0 && !/\s/.test(value[i])) {
    if (value[i] === '@') {
      const before = i === 0 ? '' : value[i - 1]
      if (i === 0 || /\s/.test(before)) {
        return { query: value.slice(i + 1, caret), tokenStart: i + 1 }
      }
      return null
    }
    i--
  }
  return null
}
