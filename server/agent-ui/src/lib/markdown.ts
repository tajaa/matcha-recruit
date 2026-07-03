function esc(s: string): string {
  const el = document.createElement('span')
  el.textContent = s
  return el.innerHTML
}

export function renderMarkdown(text: string): string {
  // Code blocks
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, _lang, code) =>
    `<pre><code>${esc(code.trim())}</code></pre>`
  )
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Headers
  text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Italic
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // Links
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>'
  )
  // Blockquote
  text = text.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
  // HR
  text = text.replace(/^---$/gm, '<hr>')
  // Checkbox lists
  text = text.replace(/^- \[x\] (.+)$/gm, '<li class="check done">$1</li>')
  text = text.replace(/^- \[ \] (.+)$/gm, '<li class="check">$1</li>')
  // Unordered lists
  text = text.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>')
  text = text.replace(/((?:<li[^>]*>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
  // Paragraphs
  text = text.replace(/\n{2,}/g, '</p><p>')
  text = text.replace(/\n/g, '<br>')
  text = `<p>${text}</p>`
  // Cleanup
  text = text.replace(/<p>\s*<\/p>/g, '')
  text = text.replace(/<p>(<(?:h[123]|pre|ul|hr|blockquote)>)/g, '$1')
  text = text.replace(/(<\/(?:h[123]|pre|ul|blockquote)>)<\/p>/g, '$1')
  text = text.replace(/<p>(<hr>)<\/p>/g, '$1')
  return text
}
