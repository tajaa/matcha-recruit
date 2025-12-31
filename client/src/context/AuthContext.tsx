import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { User, CurrentUserResponse, LoginRequest, ClientRegister, CandidateRegister, UserRole } from '../types';
import { auth, getAccessToken, clearTokens } from '../api/client';

interface AuthContextType {
  user: User | null;
  profile: CurrentUserResponse['profile'] | null;
  betaFeatures: Record<string, boolean>;
  interviewPrepTokens: number;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (data: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  registerClient: (data: ClientRegister) => Promise<void>;
  registerCandidate: (data: CandidateRegister) => Promise<void>;
  hasRole: (...roles: UserRole[]) => boolean;
  hasBetaFeature: (feature: string) => boolean;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<CurrentUserResponse['profile'] | null>(null);
  const [betaFeatures, setBetaFeatures] = useState<Record<string, boolean>>({});
  const [interviewPrepTokens, setInterviewPrepTokens] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      const data = await auth.me();
      setUser({
        id: data.user.id,
        email: data.user.email,
        role: data.user.role,
        is_active: true,
        created_at: '',
        last_login: null,
      });
      setProfile(data.profile);
      setBetaFeatures(data.user.beta_features || {});
      setInterviewPrepTokens(data.user.interview_prep_tokens || 0);
    } catch {
      clearTokens();
      setUser(null);
      setProfile(null);
      setBetaFeatures({});
      setInterviewPrepTokens(0);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = async (data: LoginRequest) => {
    const result = await auth.login(data);
    setUser(result.user);
    await loadUser(); // Load full profile
  };

  const logout = async () => {
    await auth.logout();
    setUser(null);
    setProfile(null);
  };

  const registerClient = async (data: ClientRegister) => {
    const result = await auth.registerClient(data);
    setUser(result.user);
    await loadUser();
  };

  const registerCandidate = async (data: CandidateRegister) => {
    const result = await auth.registerCandidate(data);
    setUser(result.user);
    await loadUser();
  };

  const hasRole = (...roles: UserRole[]) => {
    if (!user) return false;
    return roles.includes(user.role);
  };

  const hasBetaFeature = (feature: string) => {
    return betaFeatures[feature] === true;
  };

  const refreshUser = useCallback(async () => {
    await loadUser();
  }, [loadUser]);

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        betaFeatures,
        interviewPrepTokens,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        registerClient,
        registerCandidate,
        hasRole,
        hasBetaFeature,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
