/**
 * Scheme check only, no HTML-escaping — for React `href={...}` props (React
 * escapes attribute values itself). Returns the URL, or null when the scheme
 * is disallowed (`javascript:`, `data:`, `vbscript:`, …). Use this on ANY
 * model- or RAG-sourced URL before rendering it as a link.
 *
 * Lives in utils/ rather than work/components/panels/markdownToHtml.ts (its
 * original home) because both apps need it: the same server corpus feeds
 * work/'s MessageBubble and the matcha-side CitationSources, and a shared
 * component may not reach into work/.
 */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null
  const trimmed = url.trim()
  // Relative paths and in-page anchors carry no scheme — safe.
  if (/^(\/|#|\.\/|\.\.\/|\?)/.test(trimmed)) return trimmed
  const scheme = trimmed.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/)?.[1]?.toLowerCase()
  if (!scheme) return trimmed // no scheme → treat as relative
  if (scheme === 'http' || scheme === 'https' || scheme === 'mailto') return trimmed
  return null
}
