import { FormEvent, useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8004';
const TOKEN_KEY = 'gumm_local_access_token';

type AuthUser = {
  id: string;
  business_id: string;
  full_name: string;
  email: string;
  role: 'owner' | 'admin' | 'staff';
  is_active: boolean;
  created_at?: string;
  last_login_at?: string | null;
};

type Business = {
  id: string;
  name: string;
  slug: string;
  created_at?: string;
};

type BusinessSettings = {
  business_id: string;
  timezone: string;
  currency: string;
  sender_name: string | null;
  sender_email: string | null;
  loyalty_message: string | null;
  vip_label: string;
  created_at?: string;
  updated_at?: string;
};

type BusinessProfile = {
  business: Business;
  settings: BusinessSettings;
  media?: BusinessMedia[];
  current_user?: AuthUser;
};

type BusinessMedia = {
  id: string;
  business_id: string;
  uploaded_by: string;
  media_type: 'image' | 'video';
  media_url: string;
  mime_type: string;
  original_filename: string | null;
  size_bytes: number;
  caption: string | null;
  sort_order: number;
  created_at: string;
};

type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
  business: Business;
};

type Cafe = {
  id: string;
  name: string;
  neighborhood: string | null;
  accent_color: string;
  created_at: string;
};

type RewardProgram = {
  id: string;
  cafe_id: string;
  name: string;
  visits_required: number;
  reward_description: string;
  active: boolean;
  created_at: string;
};

type LocalCustomer = {
  id: string;
  cafe_id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  favorite_order: string | null;
  is_vip: boolean;
  notes: string | null;
  created_at: string;
  total_visits: number;
  total_rewards_redeemed: number;
};

type DashboardData = {
  totals: {
    total_locals: number;
    vip_locals: number;
    total_visits: number;
    rewards_redeemed: number;
  };
  programs: Array<{
    id: string;
    name: string;
    visits_required: number;
    reward_description: string;
    active: boolean;
    total_visits_logged: number;
    participating_locals: number;
    total_redemptions: number;
  }>;
  top_locals: Array<{
    id: string;
    full_name: string;
    is_vip: boolean;
    total_visits: number;
    total_rewards_redeemed: number;
  }>;
};

type LocalProgress = {
  local: {
    id: string;
    full_name: string;
    is_vip: boolean;
  };
  total_visits: number;
  total_rewards_redeemed: number;
  program_progress: Array<{
    program: RewardProgram;
    stamps_earned: number;
    stamps_toward_next_reward: number;
    rewards_redeemed: number;
    available_rewards: number;
    visits_required: number;
    visits_to_next_reward: number;
  }>;
};

type TeamMember = AuthUser;

type EmailCampaign = {
  id: string;
  business_id: string;
  cafe_id: string;
  created_by: string;
  created_by_name?: string;
  title: string;
  subject: string;
  body: string;
  target_segment: 'all' | 'vip' | 'regular' | 'reward_ready';
  status: 'draft' | 'sent' | 'failed' | 'simulated';
  sent_count: number;
  failure_count: number;
  created_at: string;
  sent_at: string | null;
};

type Message = {
  tone: 'success' | 'error';
  text: string;
};

type ApiOptions = {
  token?: string;
  init?: RequestInit;
};

async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.init?.headers ?? undefined);
  const requestBody = options.init?.body;
  if (!(requestBody instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (options.token) {
    headers.set('Authorization', `Bearer ${options.token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options.init,
    headers,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Non-JSON error response.
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function formatMoney(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return '--';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value);
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return '--';
  }
  return new Date(value).toLocaleString();
}

function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) ?? '');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);

  const [authMode, setAuthMode] = useState<'register' | 'login'>('register');

  const [registerBusinessName, setRegisterBusinessName] = useState('');
  const [registerOwnerName, setRegisterOwnerName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerCafeName, setRegisterCafeName] = useState('Main Cafe');
  const [registerNeighborhood, setRegisterNeighborhood] = useState('');

  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [businessMedia, setBusinessMedia] = useState<BusinessMedia[]>([]);

  const [cafes, setCafes] = useState<Cafe[]>([]);
  const [selectedCafeId, setSelectedCafeId] = useState('');
  const [programs, setPrograms] = useState<RewardProgram[]>([]);
  const [locals, setLocals] = useState<LocalCustomer[]>([]);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [campaigns, setCampaigns] = useState<EmailCampaign[]>([]);

  const [progressLocalId, setProgressLocalId] = useState('');
  const [progress, setProgress] = useState<LocalProgress | null>(null);

  const [newCafeName, setNewCafeName] = useState('');
  const [newCafeNeighborhood, setNewCafeNeighborhood] = useState('');

  const [newProgramName, setNewProgramName] = useState('Buy 9 Get 10');
  const [newProgramVisitsRequired, setNewProgramVisitsRequired] = useState(10);
  const [newProgramReward, setNewProgramReward] = useState('10th drink free');

  const [newLocalName, setNewLocalName] = useState('');
  const [newLocalPhone, setNewLocalPhone] = useState('');
  const [newLocalEmail, setNewLocalEmail] = useState('');
  const [newLocalOrder, setNewLocalOrder] = useState('');
  const [newLocalVip, setNewLocalVip] = useState(false);

  const [visitLocalId, setVisitLocalId] = useState('');
  const [visitProgramId, setVisitProgramId] = useState('');
  const [visitOrderTotal, setVisitOrderTotal] = useState('');
  const [visitNote, setVisitNote] = useState('');

  const [settingsBusinessName, setSettingsBusinessName] = useState('');
  const [settingsTimezone, setSettingsTimezone] = useState('America/Los_Angeles');
  const [settingsCurrency, setSettingsCurrency] = useState('USD');
  const [settingsSenderName, setSettingsSenderName] = useState('');
  const [settingsSenderEmail, setSettingsSenderEmail] = useState('');
  const [settingsLoyaltyMessage, setSettingsLoyaltyMessage] = useState('');
  const [settingsVipLabel, setSettingsVipLabel] = useState('Local VIP');

  const [teamName, setTeamName] = useState('');
  const [teamEmail, setTeamEmail] = useState('');
  const [teamPassword, setTeamPassword] = useState('');
  const [teamRole, setTeamRole] = useState<'admin' | 'staff'>('staff');

  const [mediaFile, setMediaFile] = useState<File | null>(null);
  const [mediaCaption, setMediaCaption] = useState('');
  const [mediaSortOrder, setMediaSortOrder] = useState(0);

  const [campaignTitle, setCampaignTitle] = useState('Weekly Local Perk');
  const [campaignSubject, setCampaignSubject] = useState('Your regulars-only offer is live');
  const [campaignBody, setCampaignBody] = useState(
    'Thanks for being one of our regulars. Show this email for a locals-only treat this week.',
  );
  const [campaignSegment, setCampaignSegment] = useState<'all' | 'vip' | 'regular' | 'reward_ready'>('all');

  const selectedCafe = useMemo(
    () => cafes.find((cafe) => cafe.id === selectedCafeId) ?? null,
    [cafes, selectedCafeId],
  );

  const canManageBusiness = currentUser?.role === 'owner' || currentUser?.role === 'admin';

  function applyBusinessProfile(profile: BusinessProfile) {
    setBusinessProfile(profile);
    if (profile.media) {
      setBusinessMedia(profile.media);
    }
    if (profile.current_user) {
      setCurrentUser(profile.current_user);
    }
    setSettingsBusinessName(profile.business.name);
    setSettingsTimezone(profile.settings.timezone || 'America/Los_Angeles');
    setSettingsCurrency(profile.settings.currency || 'USD');
    setSettingsSenderName(profile.settings.sender_name ?? profile.business.name);
    setSettingsSenderEmail(profile.settings.sender_email ?? profile.current_user?.email ?? '');
    setSettingsLoyaltyMessage(profile.settings.loyalty_message ?? '');
    setSettingsVipLabel(profile.settings.vip_label || 'Local VIP');
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    setToken('');
    setCurrentUser(null);
    setBusinessProfile(null);
    setTeamMembers([]);
    setBusinessMedia([]);
    setCafes([]);
    setPrograms([]);
    setLocals([]);
    setDashboard(null);
    setCampaigns([]);
    setSelectedCafeId('');
    setProgress(null);
    setProgressLocalId('');
    setVisitLocalId('');
    setVisitProgramId('');
    setMediaFile(null);
    setMediaCaption('');
    setMediaSortOrder(0);
  }

  async function loadBusinessCore(activeToken: string) {
    const [profile, members, cafeList, mediaList] = await Promise.all([
      apiRequest<BusinessProfile>('/api/business/profile', { token: activeToken }),
      apiRequest<TeamMember[]>('/api/business/team', { token: activeToken }),
      apiRequest<Cafe[]>('/api/cafes', { token: activeToken }),
      apiRequest<BusinessMedia[]>('/api/business/media', { token: activeToken }),
    ]);

    applyBusinessProfile(profile);
    setTeamMembers(members);
    setBusinessMedia(mediaList);
    setCafes(cafeList);

    if (cafeList.length === 0) {
      setSelectedCafeId('');
      setPrograms([]);
      setLocals([]);
      setDashboard(null);
      setCampaigns([]);
      return;
    }

    const preferredCafeId = selectedCafeId && cafeList.some((cafe) => cafe.id === selectedCafeId)
      ? selectedCafeId
      : cafeList[0].id;
    setSelectedCafeId(preferredCafeId);

    await loadCafeContext(preferredCafeId, activeToken);
  }

  async function loadCafeContext(cafeId: string, activeToken = token) {
    if (!activeToken || !cafeId) {
      return;
    }

    const [programList, localList, dashboardData, campaignList] = await Promise.all([
      apiRequest<RewardProgram[]>(`/api/cafes/${cafeId}/programs`, { token: activeToken }),
      apiRequest<LocalCustomer[]>(`/api/cafes/${cafeId}/locals`, { token: activeToken }),
      apiRequest<DashboardData>(`/api/cafes/${cafeId}/dashboard`, { token: activeToken }),
      apiRequest<EmailCampaign[]>(`/api/cafes/${cafeId}/email-campaigns`, { token: activeToken }),
    ]);

    setPrograms(programList);
    setLocals(localList);
    setDashboard(dashboardData);
    setCampaigns(campaignList);

    if (!programList.some((program) => program.id === visitProgramId)) {
      setVisitProgramId(programList[0]?.id ?? '');
    }
    if (!localList.some((local) => local.id === visitLocalId)) {
      setVisitLocalId(localList[0]?.id ?? '');
    }
  }

  async function refreshCurrentCafe(activeToken = token) {
    if (!selectedCafeId || !activeToken) {
      return;
    }

    await loadCafeContext(selectedCafeId, activeToken);

    if (progressLocalId) {
      const progressData = await apiRequest<LocalProgress>(
        `/api/cafes/${selectedCafeId}/locals/${progressLocalId}/progress`,
        { token: activeToken },
      );
      setProgress(progressData);
    }
  }

  useEffect(() => {
    async function bootstrap() {
      if (!token) {
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        await loadBusinessCore(token);
      } catch {
        clearSession();
      } finally {
        setLoading(false);
      }
    }

    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!token || !selectedCafeId) {
      return;
    }

    void loadCafeContext(selectedCafeId).catch((error: unknown) => {
      const text = error instanceof Error ? error.message : 'Failed to load cafe context';
      setMessage({ tone: 'error', text });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCafeId]);

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);

    try {
      const response = await apiRequest<AuthResponse>('/api/auth/register-business', {
        init: {
          method: 'POST',
          body: JSON.stringify({
            business_name: registerBusinessName,
            owner_name: registerOwnerName,
            owner_email: registerEmail,
            password: registerPassword,
            initial_cafe_name: registerCafeName,
            initial_neighborhood: registerNeighborhood || null,
            initial_accent_color: '#B15A38',
          }),
        },
      });

      localStorage.setItem(TOKEN_KEY, response.access_token);
      setToken(response.access_token);
      setCurrentUser(response.user);
      await loadBusinessCore(response.access_token);
      setMessage({ tone: 'success', text: `Welcome to gumm-local, ${response.business.name}.` });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Registration failed';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);

    try {
      const response = await apiRequest<AuthResponse>('/api/auth/login', {
        init: {
          method: 'POST',
          body: JSON.stringify({
            email: loginEmail,
            password: loginPassword,
          }),
        },
      });

      localStorage.setItem(TOKEN_KEY, response.access_token);
      setToken(response.access_token);
      setCurrentUser(response.user);
      await loadBusinessCore(response.access_token);
      setMessage({ tone: 'success', text: `Welcome back, ${response.user.full_name}.` });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Login failed';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    clearSession();
    setMessage({ tone: 'success', text: 'Logged out successfully.' });
  }

  async function handleCreateCafe(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !newCafeName.trim()) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const cafe = await apiRequest<Cafe>('/api/cafes', {
        token,
        init: {
          method: 'POST',
          body: JSON.stringify({
            name: newCafeName,
            neighborhood: newCafeNeighborhood || null,
            accent_color: '#B15A38',
          }),
        },
      });

      setCafes((current) => [cafe, ...current]);
      setSelectedCafeId(cafe.id);
      setNewCafeName('');
      setNewCafeNeighborhood('');
      setMessage({ tone: 'success', text: `Cafe ${cafe.name} added.` });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to add cafe';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateProgram(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest<RewardProgram>(`/api/cafes/${selectedCafeId}/programs`, {
        token,
        init: {
          method: 'POST',
          body: JSON.stringify({
            name: newProgramName,
            visits_required: newProgramVisitsRequired,
            reward_description: newProgramReward,
          }),
        },
      });

      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Reward program created.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to create program';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateLocal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedCafeId || !newLocalName.trim()) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest<LocalCustomer>(`/api/cafes/${selectedCafeId}/locals`, {
        token,
        init: {
          method: 'POST',
          body: JSON.stringify({
            full_name: newLocalName,
            phone: newLocalPhone || null,
            email: newLocalEmail || null,
            favorite_order: newLocalOrder || null,
            notes: null,
            is_vip: newLocalVip,
          }),
        },
      });

      setNewLocalName('');
      setNewLocalPhone('');
      setNewLocalEmail('');
      setNewLocalOrder('');
      setNewLocalVip(false);
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Local customer added.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to add local customer';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleRecordVisit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedCafeId || !visitLocalId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest(`/api/cafes/${selectedCafeId}/locals/${visitLocalId}/visits`, {
        token,
        init: {
          method: 'POST',
          body: JSON.stringify({
            program_id: visitProgramId || null,
            order_total: visitOrderTotal ? Number(visitOrderTotal) : null,
            visit_note: visitNote || null,
          }),
        },
      });

      setVisitOrderTotal('');
      setVisitNote('');
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Visit stamped.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to record visit';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleVip(local: LocalCustomer) {
    if (!token || !selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest(`/api/cafes/${selectedCafeId}/locals/${local.id}`, {
        token,
        init: {
          method: 'PATCH',
          body: JSON.stringify({ is_vip: !local.is_vip }),
        },
      });
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: `${local.full_name} VIP updated.` });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to update VIP status';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenProgress(localId: string) {
    if (!token || !selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const progressData = await apiRequest<LocalProgress>(`/api/cafes/${selectedCafeId}/locals/${localId}/progress`, {
        token,
      });
      setProgress(progressData);
      setProgressLocalId(localId);
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to load progress';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleRedeem(programId: string) {
    if (!token || !selectedCafeId || !progressLocalId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest(`/api/cafes/${selectedCafeId}/locals/${progressLocalId}/redeem`, {
        token,
        init: {
          method: 'POST',
          body: JSON.stringify({
            program_id: programId,
            redemption_note: 'Redeemed from gumm-local dashboard',
          }),
        },
      });

      const refreshed = await apiRequest<LocalProgress>(
        `/api/cafes/${selectedCafeId}/locals/${progressLocalId}/progress`,
        { token },
      );
      setProgress(refreshed);
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Reward redeemed.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to redeem reward';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !canManageBusiness) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const profile = await apiRequest<BusinessProfile>('/api/business/settings', {
        token,
        init: {
          method: 'PATCH',
          body: JSON.stringify({
            business_name: settingsBusinessName,
            timezone: settingsTimezone,
            currency: settingsCurrency,
            sender_name: settingsSenderName || null,
            sender_email: settingsSenderEmail || null,
            loyalty_message: settingsLoyaltyMessage || null,
            vip_label: settingsVipLabel,
          }),
        },
      });

      applyBusinessProfile(profile);
      setMessage({ tone: 'success', text: 'Business settings saved.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to save settings';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateTeamMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !canManageBusiness) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest<TeamMember>('/api/business/team', {
        token,
        init: {
          method: 'POST',
          body: JSON.stringify({
            full_name: teamName,
            email: teamEmail,
            password: teamPassword,
            role: teamRole,
          }),
        },
      });

      const members = await apiRequest<TeamMember[]>('/api/business/team', { token });
      setTeamMembers(members);
      setTeamName('');
      setTeamEmail('');
      setTeamPassword('');
      setTeamRole('staff');
      setMessage({ tone: 'success', text: 'Team member created.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to create team member';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadBusinessMedia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !mediaFile) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append('file', mediaFile);
      if (mediaCaption.trim()) {
        formData.append('caption', mediaCaption.trim());
      }
      formData.append('sort_order', String(mediaSortOrder));

      await apiRequest<BusinessMedia>('/api/business/media', {
        token,
        init: {
          method: 'POST',
          body: formData,
        },
      });

      const mediaList = await apiRequest<BusinessMedia[]>('/api/business/media', { token });
      setBusinessMedia(mediaList);
      setMediaFile(null);
      setMediaCaption('');
      setMediaSortOrder(0);
      setMessage({ tone: 'success', text: 'Business media uploaded.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to upload media';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteBusinessMedia(mediaId: string) {
    if (!token) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest<void>(`/api/business/media/${mediaId}`, {
        token,
        init: { method: 'DELETE' },
      });
      const mediaList = await apiRequest<BusinessMedia[]>('/api/business/media', { token });
      setBusinessMedia(mediaList);
      setMessage({ tone: 'success', text: 'Business media removed.' });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to delete media';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  async function handleSendCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const response = await apiRequest<{ campaign: EmailCampaign; delivery_summary: Record<string, number> }>(
        `/api/cafes/${selectedCafeId}/email-campaigns`,
        {
          token,
          init: {
            method: 'POST',
            body: JSON.stringify({
              title: campaignTitle,
              subject: campaignSubject,
              body: campaignBody,
              target_segment: campaignSegment,
              send_now: true,
            }),
          },
        },
      );

      await refreshCurrentCafe();
      setMessage({
        tone: 'success',
        text: `Campaign sent: ${response.delivery_summary.total_recipients ?? 0} recipient(s).`,
      });
    } catch (error) {
      const text = error instanceof Error ? error.message : 'Failed to send campaign';
      setMessage({ tone: 'error', text });
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="app-shell loading-shell">
        <div className="loading-card">
          <p>Booting gumm-local...</p>
        </div>
      </div>
    );
  }

  if (!token || !currentUser || !businessProfile) {
    return (
      <div className="app-shell auth-shell">
        <header className="hero">
          <div>
            <p className="eyebrow">gumm-local</p>
            <h1>Set up your neighborhood loyalty hub</h1>
            <p className="subhead">
              Register your cafe business, onboard staff, manage regular rewards, and launch local email blasts.
            </p>
          </div>
          <div className="auth-toggle">
            <button
              type="button"
              className={authMode === 'register' ? 'active' : ''}
              onClick={() => setAuthMode('register')}
            >
              Register Business
            </button>
            <button
              type="button"
              className={authMode === 'login' ? 'active' : ''}
              onClick={() => setAuthMode('login')}
            >
              Login
            </button>
          </div>
        </header>

        {message ? (
          <div className={`notice ${message.tone}`} role="status">
            {message.text}
          </div>
        ) : null}

        <section className="panel auth-panel">
          {authMode === 'register' ? (
            <form className="stack form" onSubmit={handleRegister}>
              <h2>Business Registration</h2>
              <label>
                Business name
                <input
                  value={registerBusinessName}
                  onChange={(event) => setRegisterBusinessName(event.target.value)}
                  placeholder="Gumm Local Coffee"
                  required
                />
              </label>
              <label>
                Owner full name
                <input
                  value={registerOwnerName}
                  onChange={(event) => setRegisterOwnerName(event.target.value)}
                  placeholder="Jordan Kim"
                  required
                />
              </label>
              <label>
                Owner email
                <input
                  type="email"
                  value={registerEmail}
                  onChange={(event) => setRegisterEmail(event.target.value)}
                  placeholder="owner@cafe.com"
                  required
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={registerPassword}
                  onChange={(event) => setRegisterPassword(event.target.value)}
                  placeholder="At least 8 characters"
                  minLength={8}
                  required
                />
              </label>
              <label>
                First cafe location
                <input
                  value={registerCafeName}
                  onChange={(event) => setRegisterCafeName(event.target.value)}
                  placeholder="Downtown Counter"
                  required
                />
              </label>
              <label>
                Neighborhood
                <input
                  value={registerNeighborhood}
                  onChange={(event) => setRegisterNeighborhood(event.target.value)}
                  placeholder="Mission District"
                />
              </label>
              <button disabled={busy} type="submit">Create Business Account</button>
            </form>
          ) : (
            <form className="stack form" onSubmit={handleLogin}>
              <h2>Login</h2>
              <label>
                Email
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(event) => setLoginEmail(event.target.value)}
                  placeholder="owner@cafe.com"
                  required
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  placeholder="Your password"
                  minLength={8}
                  required
                />
              </label>
              <button disabled={busy} type="submit">Sign In</button>
            </form>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="hero top-bar">
        <div>
          <p className="eyebrow">gumm-local</p>
          <h1>{businessProfile.business.name}</h1>
          <p className="subhead">
            Signed in as {currentUser.full_name} ({currentUser.email})
          </p>
        </div>
        <div className="session-actions">
          <span className="role-pill">{currentUser.role.toUpperCase()}</span>
          <button type="button" onClick={handleLogout}>Logout</button>
        </div>
      </header>

      {message ? (
        <div className={`notice ${message.tone}`} role="status">
          {message.text}
        </div>
      ) : null}

      <main className="main-grid">
        <section className="panel stack">
          <h2>Cafe + rewards</h2>
          <label>
            Active cafe
            <select value={selectedCafeId} onChange={(event) => setSelectedCafeId(event.target.value)}>
              {cafes.length === 0 ? <option value="">No cafes yet</option> : null}
              {cafes.map((cafe) => (
                <option key={cafe.id} value={cafe.id}>
                  {cafe.name}
                  {cafe.neighborhood ? ` - ${cafe.neighborhood}` : ''}
                </option>
              ))}
            </select>
          </label>

          <form onSubmit={handleCreateCafe} className="stack form muted-form">
            <h3>Add cafe location</h3>
            <label>
              Cafe name
              <input
                value={newCafeName}
                onChange={(event) => setNewCafeName(event.target.value)}
                placeholder="Beacon Street Roasters"
                required
              />
            </label>
            <label>
              Neighborhood
              <input
                value={newCafeNeighborhood}
                onChange={(event) => setNewCafeNeighborhood(event.target.value)}
                placeholder="Mission District"
              />
            </label>
            <button disabled={busy || !canManageBusiness} type="submit">Add Cafe</button>
          </form>

          <form onSubmit={handleCreateProgram} className="stack form muted-form">
            <h3>Create reward program</h3>
            <label>
              Program name
              <input
                value={newProgramName}
                onChange={(event) => setNewProgramName(event.target.value)}
                required
              />
            </label>
            <label>
              Visits needed
              <input
                type="number"
                min={1}
                max={50}
                value={newProgramVisitsRequired}
                onChange={(event) => setNewProgramVisitsRequired(Number(event.target.value))}
                required
              />
            </label>
            <label>
              Reward
              <input
                value={newProgramReward}
                onChange={(event) => setNewProgramReward(event.target.value)}
                required
              />
            </label>
            <button disabled={busy || !selectedCafeId} type="submit">Save Program</button>
          </form>
        </section>

        <section className="panel stack">
          <h2>Regular operations</h2>
          <form onSubmit={handleCreateLocal} className="stack form">
            <h3>Add local customer</h3>
            <label>
              Full name
              <input
                value={newLocalName}
                onChange={(event) => setNewLocalName(event.target.value)}
                placeholder="Avery Park"
                required
              />
            </label>
            <label>
              Phone
              <input
                value={newLocalPhone}
                onChange={(event) => setNewLocalPhone(event.target.value)}
                placeholder="(555) 123-4567"
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={newLocalEmail}
                onChange={(event) => setNewLocalEmail(event.target.value)}
                placeholder="avery@sample.com"
              />
            </label>
            <label>
              Favorite order
              <input
                value={newLocalOrder}
                onChange={(event) => setNewLocalOrder(event.target.value)}
                placeholder="Iced oat milk cortado"
              />
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={newLocalVip} onChange={(event) => setNewLocalVip(event.target.checked)} />
              Mark as VIP local
            </label>
            <button disabled={busy || !selectedCafeId} type="submit">Add Local</button>
          </form>

          <form onSubmit={handleRecordVisit} className="stack form muted-form">
            <h3>Stamp visit</h3>
            <label>
              Local
              <select value={visitLocalId} onChange={(event) => setVisitLocalId(event.target.value)} required>
                <option value="">Pick a local</option>
                {locals.map((local) => (
                  <option key={local.id} value={local.id}>{local.full_name}</option>
                ))}
              </select>
            </label>
            <label>
              Program
              <select value={visitProgramId} onChange={(event) => setVisitProgramId(event.target.value)}>
                <option value="">No program (general visit)</option>
                {programs.map((program) => (
                  <option key={program.id} value={program.id}>{program.name}</option>
                ))}
              </select>
            </label>
            <label>
              Ticket amount
              <input
                type="number"
                step="0.01"
                min={0}
                value={visitOrderTotal}
                onChange={(event) => setVisitOrderTotal(event.target.value)}
                placeholder="8.50"
              />
            </label>
            <label>
              Visit note
              <input
                value={visitNote}
                onChange={(event) => setVisitNote(event.target.value)}
                placeholder="Ordered seasonal flat white"
              />
            </label>
            <button disabled={busy || !selectedCafeId || !visitLocalId} type="submit">Record Visit</button>
          </form>
        </section>

        <section className="panel stack">
          <h2>Business settings</h2>
          <form onSubmit={handleSaveSettings} className="stack form">
            <label>
              Business name
              <input
                value={settingsBusinessName}
                onChange={(event) => setSettingsBusinessName(event.target.value)}
                required
              />
            </label>
            <div className="inline-row">
              <label>
                Timezone
                <input
                  value={settingsTimezone}
                  onChange={(event) => setSettingsTimezone(event.target.value)}
                  required
                />
              </label>
              <label>
                Currency
                <input
                  value={settingsCurrency}
                  onChange={(event) => setSettingsCurrency(event.target.value)}
                  required
                />
              </label>
            </div>
            <label>
              Sender name
              <input
                value={settingsSenderName}
                onChange={(event) => setSettingsSenderName(event.target.value)}
                placeholder="Neighborhood Team"
              />
            </label>
            <label>
              Sender email
              <input
                type="email"
                value={settingsSenderEmail}
                onChange={(event) => setSettingsSenderEmail(event.target.value)}
                placeholder="locals@cafe.com"
              />
            </label>
            <label>
              VIP label
              <input
                value={settingsVipLabel}
                onChange={(event) => setSettingsVipLabel(event.target.value)}
                placeholder="Local VIP"
              />
            </label>
            <label>
              Loyalty message
              <input
                value={settingsLoyaltyMessage}
                onChange={(event) => setSettingsLoyaltyMessage(event.target.value)}
                placeholder="Thanks for being a regular"
              />
            </label>
            <button disabled={busy || !canManageBusiness} type="submit">Save Settings</button>
          </form>

          <h3>Team members</h3>
          <div className="team-list">
            {teamMembers.map((member) => (
              <article key={member.id} className="team-row">
                <div>
                  <strong>{member.full_name}</strong>
                  <p>{member.email}</p>
                </div>
                <span className="role-pill small">{member.role}</span>
              </article>
            ))}
          </div>

          <form onSubmit={handleCreateTeamMember} className="stack form muted-form">
            <h3>Add team account</h3>
            <label>
              Full name
              <input value={teamName} onChange={(event) => setTeamName(event.target.value)} required />
            </label>
            <label>
              Email
              <input type="email" value={teamEmail} onChange={(event) => setTeamEmail(event.target.value)} required />
            </label>
            <label>
              Password
              <input
                type="password"
                minLength={8}
                value={teamPassword}
                onChange={(event) => setTeamPassword(event.target.value)}
                required
              />
            </label>
            <label>
              Role
              <select value={teamRole} onChange={(event) => setTeamRole(event.target.value as 'admin' | 'staff')}>
                <option value="staff">Staff</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <button disabled={busy || !canManageBusiness} type="submit">Create Team User</button>
          </form>

          <form onSubmit={handleUploadBusinessMedia} className="stack form muted-form">
            <h3>Business profile media</h3>
            <label>
              Upload photo or short video
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm,video/quicktime"
                onChange={(event) => setMediaFile(event.target.files?.[0] ?? null)}
                required
              />
            </label>
            <label>
              Caption
              <input
                value={mediaCaption}
                onChange={(event) => setMediaCaption(event.target.value)}
                placeholder="Downtown espresso bar scene"
              />
            </label>
            <label>
              Sort order
              <input
                type="number"
                min={0}
                max={999}
                value={mediaSortOrder}
                onChange={(event) => setMediaSortOrder(Number(event.target.value) || 0)}
              />
            </label>
            <button disabled={busy || !mediaFile} type="submit">Upload Media</button>
          </form>

          <div className="media-grid">
            {businessMedia.map((item) => (
              <article key={item.id} className="media-card">
                {item.media_type === 'image' ? (
                  <img src={item.media_url} alt={item.caption ?? 'Business media'} loading="lazy" />
                ) : (
                  <video src={item.media_url} controls preload="metadata" />
                )}
                <div className="media-meta">
                  <p>{item.caption ?? item.original_filename ?? 'Business media'}</p>
                  <span>{item.media_type.toUpperCase()} • {(item.size_bytes / (1024 * 1024)).toFixed(1)}MB</span>
                  <span>{formatDateTime(item.created_at)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteBusinessMedia(item.id)}
                  disabled={busy || !canManageBusiness}
                >
                  Delete
                </button>
              </article>
            ))}
            {businessMedia.length === 0 ? <p className="empty-copy">No profile media uploaded yet.</p> : null}
          </div>
        </section>
      </main>

      <section className="panel stack dashboard-panel">
        <h2>{selectedCafe ? `${selectedCafe.name} performance` : 'Cafe performance'}</h2>
        <div className="stat-grid">
          <article>
            <p>Locals</p>
            <strong>{dashboard?.totals.total_locals ?? 0}</strong>
          </article>
          <article>
            <p>VIP locals</p>
            <strong>{dashboard?.totals.vip_locals ?? 0}</strong>
          </article>
          <article>
            <p>Visits stamped</p>
            <strong>{dashboard?.totals.total_visits ?? 0}</strong>
          </article>
          <article>
            <p>Rewards redeemed</p>
            <strong>{dashboard?.totals.rewards_redeemed ?? 0}</strong>
          </article>
        </div>

        <div className="program-stack">
          {(dashboard?.programs ?? []).map((program) => (
            <article key={program.id} className="program-card">
              <header>
                <h3>{program.name}</h3>
                <span>{program.visits_required} visits</span>
              </header>
              <p>{program.reward_description}</p>
              <div className="program-metrics">
                <span>{program.participating_locals} locals active</span>
                <span>{program.total_redemptions} redeemed</span>
              </div>
            </article>
          ))}
          {(dashboard?.programs ?? []).length === 0 ? (
            <p className="empty-copy">No reward program yet. Add one above.</p>
          ) : null}
        </div>
      </section>

      <section className="panel locals-section">
        <h2>Locals roster</h2>
        <div className="locals-grid">
          {locals.map((local) => (
            <article key={local.id} className="local-card">
              <div>
                <h3>{local.full_name}</h3>
                <p>{local.favorite_order ?? 'No favorite order yet'}</p>
              </div>
              <div className="local-metrics">
                <span>{local.total_visits} visits</span>
                <span>{local.total_rewards_redeemed} rewards</span>
                {local.phone ? <span>{local.phone}</span> : null}
                {local.email ? <span>{local.email}</span> : null}
              </div>
              <div className="card-actions">
                <button type="button" onClick={() => handleToggleVip(local)} disabled={busy}>
                  {local.is_vip ? 'Remove VIP' : 'Make VIP'}
                </button>
                <button type="button" onClick={() => handleOpenProgress(local.id)} disabled={busy}>
                  Open Progress
                </button>
              </div>
            </article>
          ))}
          {locals.length === 0 ? <p className="empty-copy">No locals yet. Add one above.</p> : null}
        </div>
      </section>

      <section className="panel progress-section">
        <h2>Loyalty progress</h2>
        {!progress ? (
          <p className="empty-copy">Open a local to inspect reward progress and redeem perks.</p>
        ) : (
          <div className="stack">
            <header className="progress-header">
              <h3>{progress.local.full_name}</h3>
              <span>{progress.local.is_vip ? settingsVipLabel : 'Standard Local'}</span>
            </header>
            <p>
              Total visits: <strong>{progress.total_visits}</strong> | Rewards redeemed:{' '}
              <strong>{progress.total_rewards_redeemed}</strong>
            </p>
            <div className="progress-grid">
              {progress.program_progress.map((entry) => (
                <article key={entry.program.id} className="progress-card">
                  <h4>{entry.program.name}</h4>
                  <p>{entry.program.reward_description}</p>
                  <div className="program-metrics">
                    <span>{entry.stamps_earned} stamps</span>
                    <span>{entry.stamps_toward_next_reward}/{entry.visits_required} toward next</span>
                    <span>{entry.available_rewards} reward(s) available</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRedeem(entry.program.id)}
                    disabled={busy || entry.available_rewards <= 0}
                  >
                    Redeem Reward
                  </button>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="panel stack">
        <h2>Email blasts</h2>
        <form onSubmit={handleSendCampaign} className="stack form">
          <label>
            Campaign title
            <input value={campaignTitle} onChange={(event) => setCampaignTitle(event.target.value)} required />
          </label>
          <label>
            Subject
            <input value={campaignSubject} onChange={(event) => setCampaignSubject(event.target.value)} required />
          </label>
          <label>
            Segment
            <select
              value={campaignSegment}
              onChange={(event) => setCampaignSegment(event.target.value as 'all' | 'vip' | 'regular' | 'reward_ready')}
            >
              <option value="all">All locals with email</option>
              <option value="vip">VIP locals only</option>
              <option value="regular">Non-VIP locals</option>
              <option value="reward_ready">Reward-ready locals</option>
            </select>
          </label>
          <label>
            Message body
            <textarea
              className="campaign-body"
              value={campaignBody}
              onChange={(event) => setCampaignBody(event.target.value)}
              rows={5}
              required
            />
          </label>
          <button disabled={busy || !selectedCafeId} type="submit">Send Email Blast</button>
        </form>

        <h3>Recent campaigns</h3>
        <div className="campaign-list">
          {campaigns.map((campaign) => (
            <article key={campaign.id} className="campaign-card">
              <div>
                <h4>{campaign.title}</h4>
                <p>{campaign.subject}</p>
                <p>
                  Segment: {campaign.target_segment} | Status: {campaign.status}
                </p>
              </div>
              <div className="campaign-meta">
                <span>Sent: {campaign.sent_count}</span>
                <span>Failed: {campaign.failure_count}</span>
                <span>{formatDateTime(campaign.sent_at ?? campaign.created_at)}</span>
              </div>
            </article>
          ))}
          {campaigns.length === 0 ? <p className="empty-copy">No campaigns sent yet.</p> : null}
        </div>
      </section>

      <footer className="footer-note">
        <p>
          Operating {selectedCafe ? `${selectedCafe.name}${selectedCafe.neighborhood ? ` in ${selectedCafe.neighborhood}` : ''}` : 'no cafe selected'}
        </p>
        <p>Current ticket input: {formatMoney(visitOrderTotal ? Number(visitOrderTotal) : null)}</p>
      </footer>
    </div>
  );
}

export default App;
