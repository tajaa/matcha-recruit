import { scanGithubCommits, syncGithubProject } from '../api/matchaWork'

const COOLDOWN_MS = 600_000
const lastSync = new Map<string, number>()
const lastScan = new Map<string, number>()
const syncing = new Set<string>()
const scanning = new Set<string>()

// Both collab tabs share this module state. Stamp before awaiting: two tabs
// opening in the same tick must not both index the repository.
export async function autoSyncFromGithubIfStale(projectId: string, connected: boolean) {
  if (!connected || syncing.has(projectId) || (lastSync.has(projectId) && Date.now() - lastSync.get(projectId)! < COOLDOWN_MS)) return null
  syncing.add(projectId)
  lastSync.set(projectId, Date.now())
  try { return await syncGithubProject(projectId) }
  finally { syncing.delete(projectId) }
}

export async function syncGithubNow(projectId: string) {
  if (syncing.has(projectId)) return null
  syncing.add(projectId)
  lastSync.set(projectId, Date.now())
  try { return await syncGithubProject(projectId) }
  finally { syncing.delete(projectId) }
}

export async function autoScanGithubIfStale(projectId: string, connected: boolean) {
  if (!connected || scanning.has(projectId) || (lastScan.has(projectId) && Date.now() - lastScan.get(projectId)! < COOLDOWN_MS)) return null
  scanning.add(projectId)
  lastScan.set(projectId, Date.now())
  try { return await scanGithubCommits(projectId) }
  finally { scanning.delete(projectId) }
}
