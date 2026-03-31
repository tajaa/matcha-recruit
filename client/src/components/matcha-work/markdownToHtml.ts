import type { ProjectSection } from '../../types/matcha-work'

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
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
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
  if (content.startsWith('<') && (content.includes('</p>') || content.includes('</h') || content.includes('</ul>'))) return content
  return markdownToHtml(content)
}
