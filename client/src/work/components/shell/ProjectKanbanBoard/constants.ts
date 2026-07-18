import type { TaskPriority } from '../../../types'

export const PRIORITIES: TaskPriority[] = ['critical', 'high', 'medium', 'low']

export function lastSeenKey(userId: string, projectId: string): string {
  return `kanban-lastseen-${userId}-${projectId}`
}
