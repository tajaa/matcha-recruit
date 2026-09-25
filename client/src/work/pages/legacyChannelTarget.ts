export function resolveLegacyChannelTarget(
  channel: { channel_scope?: 'operations' | 'project_discussion' | 'community'; project_id?: string | null },
  channelId: string,
  search: string,
): string | null {
  if (channel.channel_scope === 'project_discussion' && channel.project_id) {
    const suffix = search ? `${search}&tab=chat` : '?tab=chat'
    return `/work/projects/${channel.project_id}${suffix}`
  }
  if (channel.channel_scope === 'operations') {
    return `/ops/channels/${channelId}${search}`
  }
  // Community channels are valid in the business shell too. Returning null
  // tells the caller to render the local channel view instead of bouncing
  // between /work and /espresso based on identity.
  return null
}
