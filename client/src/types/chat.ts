/**
 * Chat System Types
 * Standalone community chat - separate from main app auth
 */

// ====================
// User Types
// ====================

export interface ChatUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url: string | null;
  bio: string | null;
  last_seen: string;
}

export interface ChatUserRegister {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
}

export interface ChatUserLogin {
  email: string;
  password: string;
}

export interface ChatUserUpdate {
  first_name?: string;
  last_name?: string;
  bio?: string;
  avatar_url?: string;
}

// ====================
// Auth Types
// ====================

export interface ChatTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: ChatUser;
}

export interface ChatRefreshRequest {
  refresh_token: string;
}

// ====================
// Room Types
// ====================

export interface ChatRoom {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  icon: string | null;
  is_default: boolean;
  member_count: number;
  created_at: string;
}

export interface ChatRoomWithUnread extends ChatRoom {
  unread_count: number;
  is_member: boolean;
}

export interface ChatRoomMember {
  user: ChatUser;
  joined_at: string;
}

// ====================
// Message Types
// ====================

export interface ChatMessage {
  id: string;
  room_id: string;
  user_id: string | null;
  content: string;
  created_at: string;
  edited_at: string | null;
  user: ChatUser | null;
}

export interface ChatMessageCreate {
  content: string;
}

export interface ChatMessageUpdate {
  content: string;
}

export interface MessagePage {
  messages: ChatMessage[];
  next_cursor: string | null;
  has_more: boolean;
}

// ====================
// WebSocket Types
// ====================

export type WSClientMessageType = 'join_room' | 'leave_room' | 'message' | 'typing' | 'ping';
export type WSServerMessageType = 'message' | 'user_joined' | 'user_left' | 'typing' | 'online_users' | 'pong' | 'error';

export interface WSClientMessage {
  type: WSClientMessageType;
  room?: string;
  content?: string;
}

export interface WSServerMessage {
  type: WSServerMessageType;
  room?: string;
  message?: ChatMessage;
  user?: ChatUser;
  users?: ChatUser[];
  error?: string;
}

// ====================
// Helper Functions
// ====================

export function getDisplayName(user: ChatUser): string {
  return `${user.first_name} ${user.last_name}`;
}

export function getInitials(user: ChatUser): string {
  return `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase();
}

export function isOnline(user: ChatUser, thresholdMinutes: number = 5): boolean {
  const lastSeen = new Date(user.last_seen);
  const now = new Date();
  const diffMs = now.getTime() - lastSeen.getTime();
  const diffMinutes = diffMs / (1000 * 60);
  return diffMinutes < thresholdMinutes;
}

export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMinutes < 1) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
}

export function formatMessageTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
