import { cappeApi } from '../../api'

/** Follow a magazine from the account, or stop. Dashboard only: no email is
 *  sent (server/app/cappe/services/magazine/follows.py). */
export async function setFollowing(slug: string, follow: boolean): Promise<boolean> {
  const path = `/reader/magazines/${encodeURIComponent(slug)}/follow`
  const res = follow
    ? await cappeApi.put<{ following: boolean }>(path)
    : await cappeApi.delete<{ following: boolean }>(path)
  return res.following
}
