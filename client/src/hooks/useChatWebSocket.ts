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
  isReconnecting: boolean;
  joinRoom: (slug: string) => void;
  leaveRoom: (slug: string) => void;
  sendMessage: (room: string, content: string) => void;
  sendTyping: (room: string) => void;
}

// Exponential backoff constants
const MIN_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds

export function useChatWebSocket(options: UseChatWebSocketOptions = {}): UseChatWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const optionsRef = useRef(options);
  const connectRef = useRef<(() => void) | undefined>(undefined);

  // Keep options ref updated
  optionsRef.current = options;

  const scheduleReconnect = useCallback(() => {
    // Attempt to reconnect with exponential backoff if we have a token
    if (getChatAccessToken()) {
      setIsReconnecting(true);
      const delay = Math.min(
        MIN_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current),
        MAX_RECONNECT_DELAY
      );
      reconnectAttemptsRef.current += 1;

      console.log(`[Chat WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);

      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectRef.current?.();
      }, delay);
    } else {
      setIsReconnecting(false);
    }
  }, []);

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

    // Mark as reconnecting if this is a retry
    if (reconnectAttemptsRef.current > 0) {
      setIsReconnecting(true);
    }

    // Pass token as query parameter (server expects it)
    const wsUrl = `${getChatWebSocketUrl()}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setIsReconnecting(false);
      reconnectAttemptsRef.current = 0; // Reset attempts on successful connection
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

      scheduleReconnect();
    };

    ws.onerror = (event) => {
      console.error('[Chat WS] WebSocket error:', event);
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
              console.error('[Chat WS] Server error:', data.error);
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
  }, [scheduleReconnect]);

  // Keep connect ref updated for use in setTimeout
  connectRef.current = connect;

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
    setIsReconnecting(false);
    reconnectAttemptsRef.current = 0;
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Reconnect when token changes - close existing connection first to use new token
  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === 'chat_access_token') {
        // Always disconnect first to ensure clean state
        disconnect();

        if (event.newValue) {
          // Small delay to ensure disconnect completes
          setTimeout(() => {
            connect();
          }, 100);
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
    isReconnecting,
    joinRoom,
    leaveRoom,
    sendMessage,
    sendTyping,
  };
}
