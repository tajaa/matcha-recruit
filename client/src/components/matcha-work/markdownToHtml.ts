import type { ProjectSection } from '../../types/matchaWork'

/** Escape a string for safe interpolation into an HTML attribute value. */
function escapeAttr(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * Allow only http(s)/mailto and relative/anchor links. Returns the escaped
 * URL safe for an `href`, or null if the scheme is disallowed (`javascript:`,
 * `data:`, `vbscript:`, …) — content here can originate from AI output or
 * collaborators, so an unvalidated href is an XSS vector.
 */
function sanitizeHref(url: string): string | null {
  const safe = safeUrl(url)
  return safe === null ? null : escapeAttr(safe)
}

/**
 * Scheme check only, no HTML-escaping — for React `href={...}` props (React
 * escapes attribute values itself). Returns the URL, or null when the scheme
 * is disallowed (`javascript:`, `data:`, `vbscript:`, …). Use this on ANY
 * model- or RAG-sourced URL before rendering it as a link.
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

/** Convert markdown to simple HTML for TipTap initialization */
export function markdownToHtml(md: string): string {
  let html = md
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/(?<!\w)\*(.+?)\*(?!\w)/g, '<em>$1</em>')
    .replace(/(?<!\w)_(.+?)_(?!\w)/g, '<em>$1</em>')
    .replace(/^#{2}\s+(.+)$/gm, '<h2>$1</h2>')
    .replace(/^#{3}\s+(.+)$/gm, '<h3>$1</h3>')
    .replace(/^#{1}\s+(.+)$/gm, '<h2>$1</h2>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, text: string, url: string) => {
      const href = sanitizeHref(url)
      return href ? `<a href="${href}">${text}</a>` : text
    })
    .replace(/^---+$/gm, '<hr>')
    .replace(/^>\s*(.+)$/gm, '<blockquote>$1</blockquote>')

  const lines = html.split('\n')
  const result: string[] = []
  let inUl = false, inOl = false
  for (const line of lines) {
    const bulletMatch = line.match(/^[\s]*[-*]\s+(.+)/)
    const numMatch = line.match(/^[\s]*\d+\.\s+(.+)/)
    if (bulletMatch) {
      if (!inUl) { result.push('<ul>'); inUl = true }
      result.push(`<li>${bulletMatch[1]}</li>`)
    } else if (numMatch) {
      if (!inOl) { result.push('<ol>'); inOl = true }
      result.push(`<li>${numMatch[1]}</li>`)
    } else {
      if (inUl) { result.push('</ul>'); inUl = false }
      if (inOl) { result.push('</ol>'); inOl = false }
      if (line.trim() && !line.startsWith('<h') && !line.startsWith('<hr') && !line.startsWith('<blockquote')) {
        result.push(`<p>${line}</p>`)
      } else {
        result.push(line)
      }
    }
  }
  if (inUl) result.push('</ul>')
  if (inOl) result.push('</ol>')
  return result.join('\n')
}

/** Convert section content to HTML — handles both raw markdown and existing HTML */
export function sectionToHtml(s: ProjectSection): string {
  const content = s.content
  if (!content) return ''
  if (content.startsWith('<') && (content.includes('</p>') || content.includes('</h') || content.includes('</ul>') || content.includes('</ol>'))) return content
  return markdownToHtml(content)
}
