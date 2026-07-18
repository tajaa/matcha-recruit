import type { MWProjectTask } from '../types/matchaWork'

/** Tokenize a kanban search query — whitespace-split AND tokens, lowercased,
 *  with `"quoted phrases"` kept as a single token. Mirrors the desktop
 *  `KanbanSearch` tokenizer. */
export function searchTokens(query: string): string[] {
  const tokens: string[] = []
  const re = /"([^"]+)"|(\S+)/g
  let match: RegExpExecArray | null
  while ((match = re.exec(query)) !== null) {
    const token = (match[1] ?? match[2] ?? '').trim().toLowerCase()
    if (token) tokens.push(token)
  }
  return tokens
}

/** Whether every token matches somewhere in the task's searchable fields
 *  (title, description, progress note, assignee, priority, category, column),
 *  case-insensitive. Empty token list matches everything. */
export function taskMatches(task: MWProjectTask, tokens: string[]): boolean {
  if (tokens.length === 0) return true
  const haystack = [
    task.title,
    task.description ?? '',
    task.progress_note ?? '',
    task.assigned_name ?? task.assigned_email ?? '',
    task.priority,
    task.category ?? '',
    task.board_column,
  ]
    .join(' ')
    .toLowerCase()
  return tokens.every((t) => haystack.includes(t))
}
