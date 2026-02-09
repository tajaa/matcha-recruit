import { FormEvent, useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8004';

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

type Message = {
  tone: 'success' | 'error';
  text: string;
};

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Response was not JSON.
    }
    throw new Error(detail);
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

function App() {
  const [cafes, setCafes] = useState<Cafe[]>([]);
  const [selectedCafeId, setSelectedCafeId] = useState('');
  const [programs, setPrograms] = useState<RewardProgram[]>([]);
  const [locals, setLocals] = useState<LocalCustomer[]>([]);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);

  const [progressLocalId, setProgressLocalId] = useState('');
  const [progress, setProgress] = useState<LocalProgress | null>(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);

  const [newCafeName, setNewCafeName] = useState('');
  const [newCafeNeighborhood, setNewCafeNeighborhood] = useState('');

  const [newProgramName, setNewProgramName] = useState('Local Loop');
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

  const selectedCafe = useMemo(
    () => cafes.find((cafe) => cafe.id === selectedCafeId) ?? null,
    [cafes, selectedCafeId],
  );

  async function loadCafes() {
    const cafeList = await apiRequest<Cafe[]>('/api/cafes');
    setCafes(cafeList);

    if (!selectedCafeId && cafeList.length > 0) {
      setSelectedCafeId(cafeList[0].id);
      return cafeList[0].id;
    }

    if (selectedCafeId && !cafeList.some((cafe) => cafe.id === selectedCafeId) && cafeList.length > 0) {
      setSelectedCafeId(cafeList[0].id);
      return cafeList[0].id;
    }

    if (cafeList.length === 0) {
      setSelectedCafeId('');
      setPrograms([]);
      setLocals([]);
      setDashboard(null);
      setProgress(null);
      setProgressLocalId('');
      setVisitLocalId('');
      setVisitProgramId('');
    }

    return selectedCafeId;
  }

  async function loadCafeContext(cafeId: string) {
    if (!cafeId) {
      return;
    }

    const [programList, localList, dashboardData] = await Promise.all([
      apiRequest<RewardProgram[]>(`/api/cafes/${cafeId}/programs`),
      apiRequest<LocalCustomer[]>(`/api/cafes/${cafeId}/locals`),
      apiRequest<DashboardData>(`/api/cafes/${cafeId}/dashboard`),
    ]);

    setPrograms(programList);
    setLocals(localList);
    setDashboard(dashboardData);

    if (!programList.some((program) => program.id === visitProgramId)) {
      setVisitProgramId(programList[0]?.id ?? '');
    }

    if (!localList.some((local) => local.id === visitLocalId)) {
      setVisitLocalId(localList[0]?.id ?? '');
    }
  }

  async function refreshCurrentCafe() {
    if (!selectedCafeId) {
      return;
    }
    await loadCafeContext(selectedCafeId);
    if (progressLocalId) {
      const progressData = await apiRequest<LocalProgress>(
        `/api/cafes/${selectedCafeId}/locals/${progressLocalId}/progress`,
      );
      setProgress(progressData);
    }
  }

  useEffect(() => {
    async function bootstrap() {
      setLoading(true);
      try {
        const cafeId = await loadCafes();
        if (cafeId) {
          await loadCafeContext(cafeId);
        }
      } catch (error) {
        const errorText = error instanceof Error ? error.message : 'Failed to load gumm-local data';
        setMessage({ tone: 'error', text: errorText });
      } finally {
        setLoading(false);
      }
    }

    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedCafeId) {
      return;
    }

    setProgress(null);
    setProgressLocalId('');

    void loadCafeContext(selectedCafeId).catch((error: unknown) => {
      const errorText = error instanceof Error ? error.message : 'Failed to load cafe context';
      setMessage({ tone: 'error', text: errorText });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCafeId]);

  async function handleCreateCafe(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newCafeName.trim()) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const cafe = await apiRequest<Cafe>('/api/cafes', {
        method: 'POST',
        body: JSON.stringify({
          name: newCafeName,
          neighborhood: newCafeNeighborhood || null,
          accent_color: '#B15A38',
        }),
      });

      setCafes((current) => [cafe, ...current]);
      setSelectedCafeId(cafe.id);
      setNewCafeName('');
      setNewCafeNeighborhood('');
      setMessage({ tone: 'success', text: `Cafe ${cafe.name} is live.` });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to create cafe';
      setMessage({ tone: 'error', text: errorText });
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateProgram(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest<RewardProgram>(`/api/cafes/${selectedCafeId}/programs`, {
        method: 'POST',
        body: JSON.stringify({
          name: newProgramName,
          visits_required: newProgramVisitsRequired,
          reward_description: newProgramReward,
        }),
      });

      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Reward program added.' });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to create reward program';
      setMessage({ tone: 'error', text: errorText });
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateLocal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCafeId || !newLocalName.trim()) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest<LocalCustomer>(`/api/cafes/${selectedCafeId}/locals`, {
        method: 'POST',
        body: JSON.stringify({
          full_name: newLocalName,
          phone: newLocalPhone || null,
          email: newLocalEmail || null,
          favorite_order: newLocalOrder || null,
          is_vip: newLocalVip,
          notes: null,
        }),
      });

      setNewLocalName('');
      setNewLocalPhone('');
      setNewLocalEmail('');
      setNewLocalOrder('');
      setNewLocalVip(false);
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Local added to roster.' });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to add local customer';
      setMessage({ tone: 'error', text: errorText });
    } finally {
      setBusy(false);
    }
  }

  async function handleRecordVisit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCafeId || !visitLocalId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest(`/api/cafes/${selectedCafeId}/locals/${visitLocalId}/visits`, {
        method: 'POST',
        body: JSON.stringify({
          program_id: visitProgramId || null,
          order_total: visitOrderTotal ? Number(visitOrderTotal) : null,
          visit_note: visitNote || null,
        }),
      });

      setVisitOrderTotal('');
      setVisitNote('');
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Visit stamped successfully.' });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to record visit';
      setMessage({ tone: 'error', text: errorText });
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleVip(local: LocalCustomer) {
    if (!selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest(`/api/cafes/${selectedCafeId}/locals/${local.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_vip: !local.is_vip }),
      });

      await refreshCurrentCafe();
      setMessage({
        tone: 'success',
        text: `${local.full_name} is now ${!local.is_vip ? 'VIP' : 'regular'} status.`,
      });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to update VIP status';
      setMessage({ tone: 'error', text: errorText });
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenProgress(localId: string) {
    if (!selectedCafeId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const progressData = await apiRequest<LocalProgress>(
        `/api/cafes/${selectedCafeId}/locals/${localId}/progress`,
      );
      setProgress(progressData);
      setProgressLocalId(localId);
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to load loyalty progress';
      setMessage({ tone: 'error', text: errorText });
    } finally {
      setBusy(false);
    }
  }

  async function handleRedeem(programId: string) {
    if (!selectedCafeId || !progressLocalId) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await apiRequest(`/api/cafes/${selectedCafeId}/locals/${progressLocalId}/redeem`, {
        method: 'POST',
        body: JSON.stringify({
          program_id: programId,
          redemption_note: 'Redeemed in dashboard',
        }),
      });

      const refreshed = await apiRequest<LocalProgress>(
        `/api/cafes/${selectedCafeId}/locals/${progressLocalId}/progress`,
      );
      setProgress(refreshed);
      await refreshCurrentCafe();
      setMessage({ tone: 'success', text: 'Reward redeemed and logged.' });
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Failed to redeem reward';
      setMessage({ tone: 'error', text: errorText });
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

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">gumm-local</p>
          <h1>Local loyalty, neighborhood-first</h1>
          <p className="subhead">
            Turn regulars into insiders with custom reward loops, VIP flags, and simple stamp tracking.
          </p>
        </div>

        <div className="hero-control">
          <label htmlFor="cafe-select">Active cafe</label>
          <select
            id="cafe-select"
            value={selectedCafeId}
            onChange={(event) => setSelectedCafeId(event.target.value)}
          >
            {cafes.length === 0 ? <option value="">No cafes yet</option> : null}
            {cafes.map((cafe) => (
              <option key={cafe.id} value={cafe.id}>
                {cafe.name}
                {cafe.neighborhood ? ` - ${cafe.neighborhood}` : ''}
              </option>
            ))}
          </select>
        </div>
      </header>

      {message ? (
        <div className={`notice ${message.tone}`} role="status">
          {message.text}
        </div>
      ) : null}

      <main className="main-grid">
        <section className="panel stack">
          <h2>Launch a cafe</h2>
          <form onSubmit={handleCreateCafe} className="stack form">
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
            <button disabled={busy} type="submit">Add Cafe</button>
          </form>

          <h2>Reward rule</h2>
          <form onSubmit={handleCreateProgram} className="stack form muted-form">
            <label>
              Program name
              <input
                value={newProgramName}
                onChange={(event) => setNewProgramName(event.target.value)}
                placeholder="Morning Matcha Loop"
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
                placeholder="10th drink free"
                required
              />
            </label>
            <button disabled={busy || !selectedCafeId} type="submit">Save Program</button>
          </form>
        </section>

        <section className="panel stack">
          <h2>Bring in a regular</h2>
          <form onSubmit={handleCreateLocal} className="stack form">
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
                value={newLocalEmail}
                onChange={(event) => setNewLocalEmail(event.target.value)}
                placeholder="avery@sample.com"
                type="email"
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
              <input
                type="checkbox"
                checked={newLocalVip}
                onChange={(event) => setNewLocalVip(event.target.checked)}
              />
              Mark as VIP local
            </label>
            <button disabled={busy || !selectedCafeId} type="submit">Add Local</button>
          </form>

          <h2>Stamp a visit</h2>
          <form onSubmit={handleRecordVisit} className="stack form muted-form">
            <label>
              Local
              <select value={visitLocalId} onChange={(event) => setVisitLocalId(event.target.value)} required>
                <option value="">Pick a local</option>
                {locals.map((local) => (
                  <option key={local.id} value={local.id}>
                    {local.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reward program
              <select value={visitProgramId} onChange={(event) => setVisitProgramId(event.target.value)}>
                <option value="">No program (general visit)</option>
                {programs.map((program) => (
                  <option key={program.id} value={program.id}>
                    {program.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Ticket amount (optional)
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
              Note
              <input
                value={visitNote}
                onChange={(event) => setVisitNote(event.target.value)}
                placeholder="Ordered seasonal flat white"
              />
            </label>
            <button disabled={busy || !selectedCafeId || !visitLocalId} type="submit">Record Visit</button>
          </form>
        </section>

        <section className="panel stack dashboard-panel">
          <h2>{selectedCafe ? `${selectedCafe.name} pulse` : 'Cafe pulse'}</h2>

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
                  <span>{program.total_redemptions} rewards claimed</span>
                </div>
              </article>
            ))}
            {(dashboard?.programs ?? []).length === 0 ? (
              <p className="empty-copy">No reward program yet. Start with a buy-9-get-10 loop.</p>
            ) : null}
          </div>

          <div className="leaderboard">
            <h3>Neighborhood leaderboard</h3>
            {(dashboard?.top_locals ?? []).map((local) => (
              <div key={local.id} className="leaderboard-row">
                <p>
                  {local.full_name}
                  {local.is_vip ? ' - VIP' : ''}
                </p>
                <span>{local.total_visits} visits</span>
              </div>
            ))}
            {(dashboard?.top_locals ?? []).length === 0 ? (
              <p className="empty-copy">No local activity yet.</p>
            ) : null}
          </div>
        </section>
      </main>

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
          {locals.length === 0 ? <p className="empty-copy">No locals yet. Add your first regular above.</p> : null}
        </div>
      </section>

      <section className="panel progress-section">
        <h2>Loyalty progress</h2>
        {!progress ? (
          <p className="empty-copy">Pick a local to inspect live reward progress and redeem perks.</p>
        ) : (
          <div className="stack">
            <header className="progress-header">
              <h3>{progress.local.full_name}</h3>
              <span>{progress.local.is_vip ? 'VIP Local' : 'Standard Local'}</span>
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
                    <span>{entry.stamps_earned} stamps earned</span>
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

      <footer className="footer-note">
        <p>
          {selectedCafe
            ? `Operating ${selectedCafe.name}${selectedCafe.neighborhood ? ` in ${selectedCafe.neighborhood}` : ''}`
            : 'Add a cafe to begin'}
        </p>
        <p>Current ticket input: {formatMoney(visitOrderTotal ? Number(visitOrderTotal) : null)}</p>
      </footer>
    </div>
  );
}

export default App;
