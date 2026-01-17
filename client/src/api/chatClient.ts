/**
 * Chat API Client
 * Separate from main app API - uses different auth tokens
 */

import type {
  ChatUser,
  ChatUserRegister,
  ChatUserLogin,
  ChatUserUpdate,
  ChatTokenResponse,
  ChatRoom,
  ChatRoomWithUnread,
  ChatRoomMember,
  ChatMessage,
  ChatMessageCreate,
  ChatMessageUpdate,
  MessagePage,
} from '../types/chat';

const API_BASE = 'http://localhost:8001/api/chat';

// Token storage - separate from main app tokens
const CHAT_TOKEN_KEY = 'chat_access_token';
const CHAT_REFRESH_KEY = 'chat_refresh_token';

export function getChatAccessToken(): string | null {
  return localStorage.getItem(CHAT_TOKEN_KEY);
}

export function getChatRefreshToken(): string | null {
  return localStorage.getItem(CHAT_REFRESH_KEY);
}

export function setChatTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(CHAT_TOKEN_KEY, accessToken);
  localStorage.setItem(CHAT_REFRESH_KEY, refreshToken);
}

export function clearChatTokens(): void {
  localStorage.removeItem(CHAT_TOKEN_KEY);
  localStorage.removeItem(CHAT_REFRESH_KEY);
}

async function tryRefreshChatToken(): Promise<boolean> {
  const refreshToken = getChatRefreshToken();
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) return false;

    const data: ChatTokenResponse = await response.json();
    setChatTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

async function chatRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getChatAccessToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Try to refresh token
    const refreshed = await tryRefreshChatToken();
    if (refreshed) {
      // Retry original request with new token
      (headers as Record<string, string>)['Authorization'] = `Bearer ${getChatAccessToken()}`;
      const retryResponse = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });
      if (!retryResponse.ok) {
        const error = await retryResponse.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
      }
      return retryResponse.json();
    }
    // Refresh failed, clear tokens
    clearChatTokens();
    throw new Error('Session expired');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

// ====================
// Auth API
// ====================

export const chatAuth = {
  register: async (data: ChatUserRegister): Promise<ChatTokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(error.detail || 'Registration failed');
    }

    const result: ChatTokenResponse = await response.json();
    setChatTokens(result.access_token, result.refresh_token);
    return result;
  },

  login: async (data: ChatUserLogin): Promise<ChatTokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Login failed');
    }

    const result: ChatTokenResponse = await response.json();
    setChatTokens(result.access_token, result.refresh_token);
    return result;
  },

  logout: (): void => {
    clearChatTokens();
  },

  me: () => chatRequest<ChatUser>('/auth/me'),
};

// ====================
// Rooms API
// ====================

export const chatRooms = {
  list: () => chatRequest<ChatRoomWithUnread[]>('/rooms'),

  get: (slug: string) => chatRequest<ChatRoom>(`/rooms/${slug}`),

  join: (slug: string) =>
    chatRequest<{ status: string; room: string }>(`/rooms/${slug}/join`, {
      method: 'POST',
    }),

  leave: (slug: string) =>
    chatRequest<{ status: string; room: string }>(`/rooms/${slug}/leave`, {
      method: 'POST',
    }),

  getMembers: (slug: string) => chatRequest<ChatRoomMember[]>(`/rooms/${slug}/members`),

  markRead: (slug: string) =>
    chatRequest<{ status: string; room: string }>(`/rooms/${slug}/mark-read`, {
      method: 'POST',
    }),
};

// ====================
// Messages API
// ====================

export const chatMessages = {
  getMessages: (slug: string, cursor?: string, limit: number = 50) => {
    const params = new URLSearchParams();
    params.append('limit', String(limit));
    if (cursor) params.append('cursor', cursor);
    return chatRequest<MessagePage>(`/rooms/${slug}/messages?${params.toString()}`);
  },

  postMessage: (slug: string, data: ChatMessageCreate) =>
    chatRequest<ChatMessage>(`/rooms/${slug}/messages`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  editMessage: (slug: string, messageId: string, data: ChatMessageUpdate) =>
    chatRequest<ChatMessage>(`/rooms/${slug}/messages/${messageId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteMessage: (slug: string, messageId: string) =>
    chatRequest<{ status: string; message_id: string }>(`/rooms/${slug}/messages/${messageId}`, {
      method: 'DELETE',
    }),
};

// ====================
// WebSocket URL Helper
// ====================

export function getChatWebSocketUrl(): string {
  const token = getChatAccessToken();
  return `ws://localhost:8001/ws/chat?token=${token}`;
}
