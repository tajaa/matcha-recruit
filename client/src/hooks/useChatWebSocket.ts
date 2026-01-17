/**
 * Chat WebSocket Hook
 * Manages real-time connection for chat
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { ChatMessage, ChatUser, WSServerMessage, WSClientMessage } from '../types/chat';
import { getChatWebSocketUrl, getChatAccessToken } from '../api/chatClient';

interface UseChatWebSocketOptions {
  onMessage?: (message: ChatMessage, room: string) => void;
  onUserJoined?: (user: ChatUser, room: string) => void;
  onUserLeft?: (user: ChatUser, room: string) => void;
  onTyping?: (user: ChatUser, room: string) => void;
  onOnlineUsers?: (users: ChatUser[], room: string) => void;
  onError?: (error: string) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

interface UseChatWebSocketReturn {
  isConnected: boolean;
  joinRoom: (slug: string) => void;
  leaveRoom: (slug: string) => void;
  sendMessage: (room: string, content: string) => void;
  sendTyping: (room: string) => void;
}

export function useChatWebSocket(options: UseChatWebSocketOptions = {}): UseChatWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const optionsRef = useRef(options);

  // Keep options ref updated
  optionsRef.current = options;

  const connect = useCallback(() => {
    // Don't connect if no token
    const token = getChatAccessToken();
    if (!token) {
      return;
    }

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(getChatWebSocketUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      optionsRef.current.onConnect?.();

      // Start ping interval to keep connection alive
      pingIntervalRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    ws.onclose = () => {
      setIsConnected(false);
      optionsRef.current.onDisconnect?.();

      // Clear ping interval
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      // Attempt to reconnect after 3 seconds if we have a token
      if (getChatAccessToken()) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 3000);
      }
    };

    ws.onerror = () => {
      // WebSocket errors are followed by close, so we don't need to do much here
    };

    ws.onmessage = (event) => {
      try {
        const data: WSServerMessage = JSON.parse(event.data);

        switch (data.type) {
          case 'message':
            if (data.message && data.room) {
              optionsRef.current.onMessage?.(data.message, data.room);
            }
            break;

          case 'user_joined':
            if (data.user && data.room) {
              optionsRef.current.onUserJoined?.(data.user, data.room);
            }
            break;

          case 'user_left':
            if (data.user && data.room) {
              optionsRef.current.onUserLeft?.(data.user, data.room);
            }
            break;

          case 'typing':
            if (data.user && data.room) {
              optionsRef.current.onTyping?.(data.user, data.room);
            }
            break;

          case 'online_users':
            if (data.users && data.room) {
              optionsRef.current.onOnlineUsers?.(data.users, data.room);
            }
            break;

          case 'error':
            if (data.error) {
              optionsRef.current.onError?.(data.error);
            }
            break;

          case 'pong':
            // Heartbeat response, ignore
            break;
        }
      } catch (err) {
        console.error('[Chat WS] Failed to parse message:', err);
      }
    };
  }, []);

  const disconnect = useCallback(() => {
    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Clear ping interval
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }

    // Close websocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Reconnect when token changes
  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === 'chat_access_token') {
        if (event.newValue) {
          connect();
        } else {
          disconnect();
        }
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [connect, disconnect]);

  const send = useCallback((message: WSClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const joinRoom = useCallback((slug: string) => {
    send({ type: 'join_room', room: slug });
  }, [send]);

  const leaveRoom = useCallback((slug: string) => {
    send({ type: 'leave_room', room: slug });
  }, [send]);

  const sendMessage = useCallback((room: string, content: string) => {
    send({ type: 'message', room, content });
  }, [send]);

  const sendTyping = useCallback((room: string) => {
    send({ type: 'typing', room });
  }, [send]);

  return {
    isConnected,
    joinRoom,
    leaveRoom,
    sendMessage,
    sendTyping,
  };
}
