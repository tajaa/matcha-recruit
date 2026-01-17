/**
 * Chat Auth Context
 * Completely separate from main app AuthContext
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import type { ChatUser, ChatUserRegister, ChatUserLogin } from '../types/chat';
import { chatAuth, getChatAccessToken, clearChatTokens } from '../api/chatClient';

interface ChatAuthContextType {
  user: ChatUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (data: ChatUserLogin) => Promise<ChatUser>;
  register: (data: ChatUserRegister) => Promise<ChatUser>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const ChatAuthContext = createContext<ChatAuthContextType | undefined>(undefined);

export function ChatAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ChatUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const loadingRef = useRef(false);

  const loadUser = useCallback(async () => {
    const token = getChatAccessToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    // Prevent concurrent loads
    if (loadingRef.current) return;
    loadingRef.current = true;

    try {
      const userData = await chatAuth.me();
      setUser(userData);
    } catch (err) {
      // Only clear tokens for auth errors
      const isAuthError = err instanceof Error &&
        (err.message.includes('401') || err.message.includes('Unauthorized') || err.message.includes('expired'));
      if (isAuthError) {
        clearChatTokens();
      }
      setUser(null);
    } finally {
      setIsLoading(false);
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // Refresh user data when tab regains focus
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && getChatAccessToken()) {
        loadUser();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [loadUser]);

  const login = async (data: ChatUserLogin) => {
    const result = await chatAuth.login(data);
    setUser(result.user);
    return result.user;
  };

  const register = async (data: ChatUserRegister) => {
    const result = await chatAuth.register(data);
    setUser(result.user);
    return result.user;
  };

  const logout = () => {
    chatAuth.logout();
    setUser(null);
  };

  const refreshUser = useCallback(async () => {
    await loadUser();
  }, [loadUser]);

  return (
    <ChatAuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </ChatAuthContext.Provider>
  );
}

export function useChatAuth() {
  const context = useContext(ChatAuthContext);
  if (context === undefined) {
    throw new Error('useChatAuth must be used within a ChatAuthProvider');
  }
  return context;
}
