import { api, ensureFreshToken, API_BASE } from '../../api/client'

export interface ChannelSummary {
  id: string
  name: string
  slug: string
  description: string | null
  visibility: string
  channel_scope?: 'operations' | 'project_discussion' | 'community'
  category?: string | null
  location_id?: string | null
  location_name?: string | null
  member_count: number
  unread_count: number
  last_message_at: string | null
  last_message_preview: string | null
  is_member: boolean
  is_paid?: boolean
  price_cents?: number | null
  currency?: string
  /** Per-member mute — silences sound/toast except direct @mentions. */
  is_muted?: boolean
}

/** Allowed channel categories (mirrors `CHANNEL_CATEGORIES` in
 * `server/app/core/routes/channels.py`). Update both sides when adding. */
export const CHANNEL_CATEGORIES = [
  'general',
  'engineering',
  'design',
  'sales',
  'support',
  'operations',
  'marketing',
  'hr',
  'announcements',
] as const
export type ChannelCategory = typeof CHANNEL_CATEGORIES[number]
export const CHANNEL_CATEGORY_LABELS: Record<ChannelCategory, string> = {
  general: 'General',
  engineering: 'Engineering',
  design: 'Design',
  sales: 'Sales',
  support: 'Support',
  operations: 'Operations',
  marketing: 'Marketing',
  hr: 'HR',
  announcements: 'Announcements',
}

export interface ChannelMember {
  user_id: string
  name: string
  email: string
  role: string
  channel_role: string // owner, moderator, member
  avatar_url: string | null
  joined_at: string
}

export interface ChannelAttachment {
  url: string
  filename: string
  content_type: string
  size: number
}

export interface ChannelReaction {
  emoji: string
  user_ids: string[]
  count: number
}

/** Quoted preview of the message a reply points at. Server always includes
 *  this on a message whose reply_to_id resolves to a real, same-channel
 *  target (see channels_ws.py's reply_uuid channel-scope check) — sender_name
 *  falls back to 'Huume' server-side when the target is a system message. */
export interface ReplyPreview {
  id: string
  sender_name: string
  content: string
  attachments?: ChannelAttachment[]
}

export interface ChannelMessage {
  id: string
  channel_id: string
  // null for system (Huume) messages — they have no sender to attribute.
  sender_id: string | null
  sender_name: string
  sender_avatar_url: string | null
  content: string
  // 'system' = a Huume-posted confirmation (EMS). Absent/undefined on
  // messages fetched before this field shipped — treat as 'user'.
  message_type?: 'user' | 'system'
  /** Structured pointer to an actionable domain record, when present. */
  metadata?: {
    action?: {
      kind: 'event_draft' | 'event' | 'event_assignment' | 'project_task' | 'schedule_proposal' | 'inventory_order'
      id: string
      status?: string
    }
    [key: string]: unknown
  }
  attachments?: ChannelAttachment[]
  reactions?: ChannelReaction[]
  created_at: string
  edited_at: string | null
  deleted_at?: string | null
  deleted_by?: string | null
  /** Message this one is threaded as a reply to. Server accepts this on send
   * and echoes it back on every broadcast/REST fetch alongside reply_preview
   * — see channels_ws.py:reply_to_id / channels.py:_MSG_SELECT. */
  reply_to_id?: string | null
  reply_preview?: ReplyPreview | null
  /** User IDs that the server resolved from @mentions in `content`. Optional —
   * older REST-fetched messages from before the mention pipeline shipped will
   * not have this field; renderers should treat absence as "no mentions
   * resolved" but may still parse `@handle` patterns in `content` for display. */
  mentioned_user_ids?: string[]
  /** Client-generated correlation ID, echoed on the WS broadcast AND now
   * returned by REST (get_channel/get_channel_messages) — used to reconcile
   * a still-pending local row against a reconnect refetch's persisted copy
   * (see channelMessages.mergeMessages). */
  client_message_id?: string | null
  /** Local-only flag set by the optimistic-send path. Never present in
   * server-broadcast or REST-fetched messages. */
  pending?: boolean
  /** Local-only: pending send that got no echo within 8s (or was queued to
   * the outbox while offline). Renders a retry affordance. */
  failed?: boolean
}

export interface ChannelDetail {
  id: string
  name: string
  slug: string
  description: string | null
  visibility: string
  channel_scope?: 'operations' | 'project_discussion' | 'community'
  category?: string | null
  location_id?: string | null
  location_name?: string | null
  is_paid: boolean
  price_cents: number | null
  currency: string
  is_archived: boolean
  created_by: string
  created_at: string
  member_count: number
  is_member: boolean
  my_role: string | null // owner, moderator, member
  members: ChannelMember[]
  messages: ChannelMessage[]
}

export const listChannels = (params?: { scope?: 'operations' | 'project_discussion' | 'community' }) => {
  const query = params?.scope ? `?scope=${encodeURIComponent(params.scope)}` : ''
  return api.get<ChannelSummary[]>(`/channels${query}`)
}

export const discoverChannels = (params?: { q?: string; paid_only?: boolean; category?: string }) => {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.paid_only) qs.set('paid_only', 'true')
  if (params?.category) qs.set('category', params.category)
  const query = qs.toString()
  return api.get<ChannelSummary[]>(`/channels/discover${query ? '?' + query : ''}`)
}

export interface PaidChannelConfig {
  price_cents: number
  currency?: string
  inactivity_threshold_days?: number | null
  inactivity_warning_days?: number
}

export interface ChannelPaymentInfo {
  is_paid: boolean
  price_cents?: number
  currency?: string
  inactivity_threshold_days?: number | null
  inactivity_warning_days?: number
  is_subscribed?: boolean
  subscription_status?: string | null
  paid_through?: string | null
  can_rejoin?: boolean
  cooldown_until?: string | null
  days_until_removal?: number | null
}

export interface MemberActivity {
  user_id: string
  name: string
  email: string
  role: string
  last_contributed_at: string | null
  subscription_status: string | null
  days_until_removal: number | null
  activity_status: string // 'active' | 'at_risk' | 'warned' | 'expired' | 'exempt'
}

export interface ChannelRevenue {
  subscriber_count: number
  mrr_cents: number
  total_revenue_cents: number
  currency: string
  recent_events: { event_type: string; amount_cents: number; created_at: string; user_id: string }[]
}

export const CHANNELS_CHANGED_EVENT = 'mw-channels-changed'

export const createChannel = async (
  name: string,
  description?: string,
  visibility: string = 'public',
  paidConfig?: PaidChannelConfig,
  category?: string,
  locationId?: string,
) => {
  const res = await api.post<ChannelDetail>('/channels', {
    name, description, visibility, category, paid_config: paidConfig, location_id: locationId,
  })
  window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
  return res
}

export const getChannel = (id: string) =>
  api.get<ChannelDetail>(`/channels/${id}`)

export const getChannelMessages = (id: string, before?: string, beforeId?: string) => {
  const qs = new URLSearchParams()
  if (before) qs.set('before', before)
  if (beforeId) qs.set('before_id', beforeId)
  const q = qs.toString()
  return api.get<ChannelMessage[]>(`/channels/${id}/messages${q ? `?${q}` : ''}`)
}

export const deleteChannelMessage = (channelId: string, messageId: string) =>
  api.delete<{ ok: boolean }>(`/channels/${channelId}/messages/${messageId}`)

export const setChannelMute = async (id: string, muted: boolean) => {
  const res = await api.post<{ ok: boolean; muted: boolean }>(`/channels/${id}/mute`, { muted })
  window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
  return res
}

export const joinChannel = async (id: string) => {
  const res = await api.post(`/channels/${id}/join`)
  window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
  return res
}

export const addChannelMembers = (id: string, userIds: string[]) =>
  api.post(`/channels/${id}/members`, { user_ids: userIds })

export const leaveChannel = async (id: string) => {
  const res = await api.post(`/channels/${id}/leave`)
  window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
  return res
}

export const updateChannel = (
  id: string,
  updates: { name?: string; description?: string; visibility?: string; category?: string; location_id?: string | null },
) => api.patch<ChannelSummary>(`/channels/${id}`, updates)

export interface ChannelLocation {
  id: string
  name: string
  city: string | null
  state: string | null
}

export const listChannelLocations = () =>
  api.get<ChannelLocation[]>('/channels/locations')

export async function uploadChannelFiles(channelId: string, files: File[]): Promise<ChannelAttachment[]> {
  const token = await ensureFreshToken()
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  const res = await fetch(`${API_BASE}/channels/${channelId}/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!res.ok) throw new Error('Upload failed')
  const data = await res.json()
  return data.attachments
}

export const kickMember = (channelId: string, userId: string) =>
  api.delete(`/channels/${channelId}/members/${userId}`)

export const setMemberRole = (channelId: string, userId: string, role: 'moderator' | 'member') =>
  api.patch(`/channels/${channelId}/members/${userId}`, { role })

export const transferOwnership = (channelId: string, userId: string) =>
  api.post(`/channels/${channelId}/transfer-ownership`, { user_id: userId })

export const searchInvitableUsers = (q: string, channelId?: string) =>
  api.get<{ id: string; name: string; email: string; role: string; avatar_url: string | null }[]>(
    `/channels/invitable-users?q=${encodeURIComponent(q)}${channelId ? `&channel_id=${encodeURIComponent(channelId)}` : ''}`
  )

export const getChannelPaymentInfo = (id: string) =>
  api.get<ChannelPaymentInfo>(`/channels/${id}/payment-info`)

export const createChannelCheckout = (id: string) =>
  api.post<{ checkout_url: string }>(`/channels/${id}/checkout`)

export const cancelChannelSubscription = (id: string) =>
  api.post<{ ok: boolean; paid_through: string }>(`/channels/${id}/cancel-subscription`)

export const updatePaidSettings = (id: string, settings: { inactivity_threshold_days?: number; inactivity_warning_days?: number }) =>
  api.patch(`/channels/${id}/paid-settings`, settings)

export const updateChannelPrice = (id: string, priceCents: number) =>
  api.patch<{ ok: boolean; price_cents: number; stripe_price_id?: string; unchanged?: boolean }>(
    `/channels/${id}/price`,
    { price_cents: priceCents },
  )

export const getMemberActivity = (id: string) =>
  api.get<MemberActivity[]>(`/channels/${id}/member-activity`)

export const getChannelRevenue = (id: string) =>
  api.get<ChannelRevenue>(`/channels/${id}/revenue`)

export interface ChannelAnalytics {
  subscribers: {
    total: number
    active: number
    past_due: number
    canceled: number
  }
  revenue: {
    mrr_cents: number
    total_subscription_cents: number
    total_tips_cents: number
    total_cents: number
  }
  activity: {
    messages_today: number
    messages_this_week: number
    messages_this_month: number
    most_active_members: {
      user_id: string
      name: string
      message_count: number
      last_active: string
    }[]
  }
  engagement: {
    avg_messages_per_day: number
    members_at_risk: number
    recent_removals: number
  }
  tips: {
    total_cents: number
    tip_count: number
    recent: {
      sender_name: string
      amount_cents: number
      message: string
      created_at: string
    }[]
  }
}

export const getChannelAnalytics = (id: string) =>
  api.get<ChannelAnalytics>(`/channels/${id}/analytics`)

export interface ChannelInvite {
  id: string
  code: string
  url: string
  max_uses: number | null
  use_count: number
  expires_at: string | null
  note: string | null
  is_active: boolean
  created_at: string
}

export const createChannelInvite = (channelId: string, options?: {
  max_uses?: number | null
  expires_in_hours?: number | null
  note?: string | null
}) => api.post<ChannelInvite>(`/channels/${channelId}/invites`, options ?? {})

export const listChannelInvites = (channelId: string) =>
  api.get<ChannelInvite[]>(`/channels/${channelId}/invites`)

export const revokeChannelInvite = (channelId: string, inviteId: string) =>
  api.delete(`/channels/${channelId}/invites/${inviteId}`)

export const sendChannelTip = (channelId: string, amountCents: number, message?: string) =>
  api.post<{ checkout_url: string }>(`/channels/${channelId}/tip`, {
    amount_cents: amountCents,
    message: message || null,
  })

export const joinByInvite = (code: string) =>
  api.post<{ ok?: boolean; requires_payment?: boolean; channel_id?: string; checkout_url?: string }>(`/channels/join-by-invite/${encodeURIComponent(code)}`)

// ---------------------------------------------------------------------------
// Email invites — invite people who don't have an account yet.
// ---------------------------------------------------------------------------

export interface EmailInviteResult {
  invited: string[]
  already_members: string[]
  failed: string[]
}

/** Owner/moderator: email free-signup links to people without an account. */
export const sendChannelEmailInvites = (channelId: string, emails: string[]) =>
  api.post<EmailInviteResult>(`/channels/${channelId}/email-invites`, { emails })

export interface ChannelInviteInfo {
  channel_name: string
  inviter_name?: string | null
  email?: string | null
  is_paid: boolean
  valid: boolean
}

export interface AcceptInviteResponse {
  access_token: string
  refresh_token: string
  channel_id: string
}

/** Public (no auth): channel context for the join landing page. */
export const getChannelInviteInfo = async (code: string): Promise<ChannelInviteInfo> => {
  const res = await fetch(`${API_BASE}/channels/invite-info/${code}`)
  if (!res.ok) throw new Error('Could not load invite')
  return res.json()
}

/** Public (no auth): create a free account + join the channel in one step.
 *  `email` is required only for unbound (shareable-link) invites; email-bound
 *  invites ignore it and use the locked address. */
export const acceptChannelInvite = async (
  code: string,
  body: { name: string; password: string; email?: string },
): Promise<AcceptInviteResponse> => {
  const res = await fetch(`${API_BASE}/channels/invite/${code}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data?.detail ?? 'Could not join channel') as Error & { status?: number }
    err.status = res.status
    throw err
  }
  return data
}

// ---------------------------------------------------------------------------
// Connections
// ---------------------------------------------------------------------------

export interface UserConnection {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  created_at: string
}

export const listConnections = () =>
  api.get<UserConnection[]>('/channels/connections')

export const listPendingConnections = () =>
  api.get<UserConnection[]>('/channels/connections/pending')

export const listSentConnections = () =>
  api.get<UserConnection[]>('/channels/connections/sent')

export const sendConnectionRequest = (userId: string) =>
  api.post<{ ok: boolean; status?: string }>('/channels/connections/request', { user_id: userId })

export const acceptConnection = (userId: string) =>
  api.post<{ ok: boolean }>('/channels/connections/accept', { user_id: userId })

export const declineConnection = (userId: string) =>
  api.post<{ ok: boolean }>('/channels/connections/decline', { user_id: userId })

export const blockConnection = (userId: string) =>
  api.post<{ ok: boolean }>('/channels/connections/block', { user_id: userId })

export interface ChannelSubscription {
  channel_id: string
  channel_name: string
  price_cents: number
  currency: string
  subscription_status: string | null
  paid_through: string | null
  days_until_removal: number | null
  removed_for_inactivity: boolean
  cooldown_until: string | null
}

export interface PaymentEvent {
  event_type: string
  amount_cents: number
  created_at: string
  channel_id: string
  channel_name: string
}

export const getMyChannelBilling = () =>
  api.get<ChannelSubscription[]>('/channels/billing')

export const getMyPaymentHistory = () =>
  api.get<PaymentEvent[]>('/channels/billing/history')
