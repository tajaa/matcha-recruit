import { listProjectFiles } from '../api/matchaWork'
import { safeFileHref } from '../hooks/useStars'

/** Fetch a fresh signed URL after the click; saved file links can expire. */
export async function openProjectFile(projectId: string, fileId: string): Promise<boolean> {
  const tab = window.open('about:blank', '_blank')
  if (!tab) return false
  tab.opener = null
  try {
    const file = (await listProjectFiles(projectId)).find((item) => item.id === fileId)
    if (!file || !safeFileHref(file.storage_url)) throw new Error('File unavailable')
    tab.location.href = file.storage_url
    return true
  } catch {
    tab.close()
    return false
  }
}
