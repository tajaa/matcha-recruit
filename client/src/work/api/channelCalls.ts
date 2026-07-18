import { api } from '../../api/client'

// Typed wrappers for the LiveKit SFU channel-call endpoints
// (server/app/core/routes/channel_calls.py). The web client never needs the
// LiveKit URL/key/secret — the server mints a token and returns the url, so a
// valid token + url arrive in the start/token responses.

export type CallMode = 'invite_only' | 'members'

export interface CallStartResponse {
  call_id: string
  livekit_url: string
  token: string
  room: string
  mode: CallMode
  max_participants: number
  max_duration_seconds: number
}

export interface CallTokenResponse {
  livekit_url: string
  token: string
  room: string
  mode: CallMode
  elapsed_seconds: number
  max_participants: number
}

export interface CallStatusResponse {
  active: boolean
  call_id?: string
  mode?: CallMode
  started_by?: string
  started_at?: string
  elapsed_seconds?: number
  participant_ids?: string[]
  invited_user_ids?: string[]
  max_participants?: number
}

export function startCall(
  channelId: string,
  body: { mode?: CallMode; invited_user_ids?: string[] } = {},
): Promise<CallStartResponse> {
  return api.post<CallStartResponse>(`/channels/${channelId}/call/start`, {
    mode: body.mode ?? 'members',
    ...(body.invited_user_ids ? { invited_user_ids: body.invited_user_ids } : {}),
  })
}

export function getCallToken(channelId: string): Promise<CallTokenResponse> {
  return api.get<CallTokenResponse>(`/channels/${channelId}/call/token`)
}

export function getCallStatus(channelId: string): Promise<CallStatusResponse> {
  return api.get<CallStatusResponse>(`/channels/${channelId}/call`)
}

export function inviteToCall(channelId: string, userIds: string[]): Promise<{ ok: boolean; invited: string[] }> {
  return api.post(`/channels/${channelId}/call/invite`, { user_ids: userIds })
}

export function stopCall(channelId: string): Promise<{ ok: boolean }> {
  return api.post(`/channels/${channelId}/call/stop`, {})
}
