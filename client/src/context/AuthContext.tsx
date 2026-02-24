import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import type {
  User,
  CurrentUserResponse,
  LoginRequest,
  BusinessRegister,
  CandidateRegister,
  UserRole,
  EnabledFeatures,
} from '../types';
import { auth, adminPlatformSettings, getAccessToken, clearTokens } from '../api/client';

interface AuthContextType {
  user: User | null;
  profile: CurrentUserResponse['profile'] | null;
  betaFeatures: Record<string, boolean>;
  interviewPrepTokens: number;
  allowedInterviewRoles: string[];
  companyFeatures: EnabledFeatures;
  onboardingNeeded: Record<string, boolean>;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (data: LoginRequest) => Promise<User>;
  logout: () => Promise<void>;
  registerBusiness: (data: BusinessRegister) => Promise<void>;
  registerCandidate: (data: CandidateRegister) => Promise<void>;
  hasRole: (...roles: UserRole[]) => boolean;
  hasBetaFeature: (feature: string) => boolean;
  hasFeature: (feature: string) => boolean;
  refreshUser: () => Promise<void>;
  platformFeatures: Set<string>;
  setPlatformFeatures: (features: Set<string>) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<CurrentUserResponse['profile'] | null>(null);
  const [betaFeatures, setBetaFeatures] = useState<Record<string, boolean>>({});
  const [interviewPrepTokens, setInterviewPrepTokens] = useState(0);
  const [allowedInterviewRoles, setAllowedInterviewRoles] = useState<string[]>([]);
  const [companyFeatures, setCompanyFeatures] = useState<EnabledFeatures>({});
  const [onboardingNeeded, setOnboardingNeeded] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [platformFeatures, setPlatformFeatures] = useState<Set<string>>(new Set());
  const loadingRef = useRef(false);

  const extractCompanyFeatures = (profileData: any): EnabledFeatures => {
    if (profileData?.enabled_features) {
      return profileData.enabled_features;
    }
    return {};
  };

  const loadUser = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    // Prevent concurrent loads
    if (loadingRef.current) return;
    loadingRef.current = true;

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
      setAllowedInterviewRoles(data.user.allowed_interview_roles || []);
      setCompanyFeatures(extractCompanyFeatures(data.profile));
      setOnboardingNeeded(data.onboarding_needed || {});
      // visible_features is now returned for all roles directly in /auth/me
      if (Array.isArray(data.visible_features)) {
        setPlatformFeatures(new Set(data.visible_features));
      }
    } catch (err) {
      // Only clear tokens and user for auth errors (401), not server errors
      const isAuthError = err instanceof Error &&
        (err.message.includes('401') || err.message.includes('Unauthorized') || err.message.includes('expired'));
      if (isAuthError) {
        clearTokens();
        setUser(null);
        setProfile(null);
        setBetaFeatures({});
        setInterviewPrepTokens(0);
        setAllowedInterviewRoles([]);
        setCompanyFeatures({});
        setOnboardingNeeded({});
      } else {
        // For non-auth errors (500s, network issues), log but don't clear user
        console.warn('Failed to load user profile:', err);
      }
    } finally {
      setIsLoading(false);
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // Refresh user data when tab regains focus to pick up admin changes (like beta access)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && getAccessToken()) {
        loadUser();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [loadUser]);

  const login = async (data: LoginRequest) => {
    setIsLoading(true);
    try {
      const result = await auth.login(data);
      // Set user immediately from login response
      setUser(result.user);

      // Try to load full profile, but don't fail login if this errors
      try {
        const profileData = await auth.me();
        setUser({
          id: profileData.user.id,
          email: profileData.user.email,
          role: profileData.user.role,
          is_active: true,
          created_at: '',
          last_login: null,
        });
        setProfile(profileData.profile);
        setBetaFeatures(profileData.user.beta_features || {});
        setInterviewPrepTokens(profileData.user.interview_prep_tokens || 0);
        setAllowedInterviewRoles(profileData.user.allowed_interview_roles || []);
        setCompanyFeatures(extractCompanyFeatures(profileData.profile));
        setOnboardingNeeded(profileData.onboarding_needed || {});
        if (Array.isArray(profileData.visible_features)) {
          setPlatformFeatures(new Set(profileData.visible_features));
        }
      } catch (err) {
        // Profile load failed, but login succeeded - keep the basic user info
        console.warn('Failed to load full profile after login:', err);
      }

      return result.user;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    await auth.logout();
    setUser(null);
    setProfile(null);
    setCompanyFeatures({});
    setOnboardingNeeded({});
    setPlatformFeatures(new Set());
  };

  const registerBusiness = async (data: BusinessRegister) => {
    const result = await auth.registerBusiness(data);
    setUser(result.user);
    // Try to load full profile, but don't fail registration if this errors
    try {
      await loadUser();
    } catch (err) {
      console.warn('Failed to load full profile after registration:', err);
    }
  };

  const registerCandidate = async (data: CandidateRegister) => {
    const result = await auth.registerCandidate(data);
    setUser(result.user);
    // Try to load full profile, but don't fail registration if this errors
    try {
      await loadUser();
    } catch (err) {
      console.warn('Failed to load full profile after registration:', err);
    }
  };

  const hasRole = (...roles: UserRole[]) => {
    if (!user) return false;
    return roles.includes(user.role);
  };

  const hasBetaFeature = (feature: string) => {
    return betaFeatures[feature] === true;
  };

  const hasFeature = (feature: string) => {
    // Admin always sees everything
    if (user?.role === 'admin') return true;
    return companyFeatures[feature] === true;
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
        allowedInterviewRoles,
        companyFeatures,
        onboardingNeeded,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        registerBusiness,
        registerCandidate,
        hasRole,
        hasBetaFeature,
        hasFeature,
        refreshUser,
        platformFeatures,
        setPlatformFeatures,
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
