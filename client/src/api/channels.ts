import { api } from './client'

export interface ChannelSummary {
  id: string
  name: string
  slug: string
  description: string | null
  visibility: string
  member_count: number
  unread_count: number
  last_message_at: string | null
  last_message_preview: string | null
  is_member: boolean
  is_paid?: boolean
  price_cents?: number | null
  currency?: string
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

export interface ChannelMessage {
  id: string
  channel_id: string
  sender_id: string
  sender_name: string
  sender_avatar_url: string | null
  content: string
  attachments?: ChannelAttachment[]
  created_at: string
  edited_at: string | null
}

export interface ChannelDetail {
  id: string
  name: string
  slug: string
  description: string | null
  visibility: string
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

export const listChannels = () =>
  api.get<ChannelSummary[]>('/channels')

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

export const createChannel = (name: string, description?: string, visibility: string = 'public', paidConfig?: PaidChannelConfig) =>
  api.post<ChannelDetail>('/channels', { name, description, visibility, paid_config: paidConfig })

export const getChannel = (id: string) =>
  api.get<ChannelDetail>(`/channels/${id}`)

export const getChannelMessages = (id: string, before?: string) =>
  api.get<ChannelMessage[]>(`/channels/${id}/messages${before ? `?before=${before}` : ''}`)

export const joinChannel = (id: string) =>
  api.post(`/channels/${id}/join`)

export const addChannelMembers = (id: string, userIds: string[]) =>
  api.post(`/channels/${id}/members`, { user_ids: userIds })

export const leaveChannel = (id: string) =>
  api.post(`/channels/${id}/leave`)

export const updateChannel = (id: string, updates: { name?: string; description?: string }) =>
  api.patch<ChannelSummary>(`/channels/${id}`, updates)

export async function uploadChannelFiles(channelId: string, files: File[]): Promise<ChannelAttachment[]> {
  const BASE = import.meta.env.VITE_API_URL ?? '/api'
  const token = localStorage.getItem('matcha_access_token')
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  const res = await fetch(`${BASE}/channels/${channelId}/upload`, {
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
    `/channels/invitable-users?q=${encodeURIComponent(q)}${channelId ? `&channel_id=${channelId}` : ''}`
  )

export const getChannelPaymentInfo = (id: string) =>
  api.get<ChannelPaymentInfo>(`/channels/${id}/payment-info`)

export const createChannelCheckout = (id: string) =>
  api.post<{ checkout_url: string }>(`/channels/${id}/checkout`)

export const cancelChannelSubscription = (id: string) =>
  api.post<{ ok: boolean; paid_through: string }>(`/channels/${id}/cancel-subscription`)

export const updatePaidSettings = (id: string, settings: { inactivity_threshold_days?: number; inactivity_warning_days?: number }) =>
  api.patch(`/channels/${id}/paid-settings`, settings)

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
  api.post<{ ok?: boolean; requires_payment?: boolean; channel_id?: string; checkout_url?: string }>(`/channels/join-by-invite/${code}`)

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
