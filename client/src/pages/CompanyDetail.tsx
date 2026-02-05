import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardHeader, CardContent, Modal, PositionCard, PositionForm } from '../components';
import { companies as companiesApi, interviews as interviewsApi, matching as matchingApi, positions as positionsApi } from '../api/client';
import { complianceAPI } from '../api/compliance';
import type { BusinessLocation, LocationCreate, JurisdictionOption } from '../api/compliance';
import { useAuth } from '../context/AuthContext';
import type { Company, Interview, MatchResult, Position } from '../types';
import { MapPin, Plus, Edit2, Trash2, X, Shield } from 'lucide-react';

const US_STATES = [
  { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' },
  { value: 'AZ', label: 'Arizona' }, { value: 'AR', label: 'Arkansas' },
  { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' },
  { value: 'FL', label: 'Florida' }, { value: 'GA', label: 'Georgia' },
  { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' },
  { value: 'IA', label: 'Iowa' }, { value: 'KS', label: 'Kansas' },
  { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' },
  { value: 'MA', label: 'Massachusetts' }, { value: 'MI', label: 'Michigan' },
  { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' },
  { value: 'NE', label: 'Nebraska' }, { value: 'NV', label: 'Nevada' },
  { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' },
  { value: 'NC', label: 'North Carolina' }, { value: 'ND', label: 'North Dakota' },
  { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' },
  { value: 'RI', label: 'Rhode Island' }, { value: 'SC', label: 'South Carolina' },
  { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' },
  { value: 'VT', label: 'Vermont' }, { value: 'VA', label: 'Virginia' },
  { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' },
  { value: 'DC', label: 'Washington D.C.' }
];

const emptyShopForm = { name: '', address: '', city: '', state: '', county: '', zipcode: '', jurisdictionKey: '' };

export function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hasFeature } = useAuth();
  const [company, setCompany] = useState<Company | null>(null);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInterviewModal, setShowInterviewModal] = useState(false);
  const [showTranscriptModal, setShowTranscriptModal] = useState(false);
  const [showPositionModal, setShowPositionModal] = useState(false);
  const [selectedInterview, setSelectedInterview] = useState<Interview | null>(null);
  const [interviewForm, setInterviewForm] = useState({ interviewer_name: '', interviewer_role: '' });
  const [aggregating, setAggregating] = useState(false);
  const [matching, setMatching] = useState(false);
  const [creatingPosition, setCreatingPosition] = useState(false);

  // IR Guidance Blurb state
  const [editingIRGuidance, setEditingIRGuidance] = useState(false);
  const [irGuidanceBlurb, setIrGuidanceBlurb] = useState('');
  const [savingIRGuidance, setSavingIRGuidance] = useState(false);

  // Shops state
  const [shops, setShops] = useState<BusinessLocation[]>([]);
  const [showShopModal, setShowShopModal] = useState(false);
  const [editingShop, setEditingShop] = useState<BusinessLocation | null>(null);
  const [shopSaving, setShopSaving] = useState(false);
  const [shopForm, setShopForm] = useState(emptyShopForm);
  const [useManualEntry, setUseManualEntry] = useState(false);
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([]);
  const [jurisdictionSearch, setJurisdictionSearch] = useState('');

  const jurisdictionsByState = useMemo(() => {
    const grouped: Record<string, JurisdictionOption[]> = {};
    for (const j of jurisdictions) {
      if (!grouped[j.state]) grouped[j.state] = [];
      grouped[j.state].push(j);
    }
    return grouped;
  }, [jurisdictions]);

  const filteredJurisdictions = useMemo(() => {
    const search = jurisdictionSearch.toLowerCase().trim();
    if (!search) return jurisdictionsByState;
    const filtered: Record<string, JurisdictionOption[]> = {};
    for (const [state, items] of Object.entries(jurisdictionsByState)) {
      const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
      const matches = items.filter(j =>
        j.city.toLowerCase().includes(search) ||
        state.toLowerCase().includes(search) ||
        stateLabel.toLowerCase().includes(search)
      );
      if (matches.length > 0) filtered[state] = matches;
    }
    return filtered;
  }, [jurisdictions, jurisdictionSearch, jurisdictionsByState]);

  const makeJurisdictionKey = (j: JurisdictionOption) => `${j.city}|${j.state}|${j.county || ''}`;

  const fetchData = async () => {
    if (!id) return;
    try {
      const [companyData, interviewsData, matchesData, positionsData, shopsData] = await Promise.all([
        companiesApi.get(id),
        interviewsApi.list(id),
        matchingApi.list(id).catch(() => []),
        positionsApi.listByCompany(id).catch(() => []),
        complianceAPI.getLocations(id).catch(() => []),
      ]);
      setCompany(companyData);
      setInterviews(interviewsData);
      setMatches(matchesData);
      setPositions(positionsData);
      setShops(shopsData);
      setIrGuidanceBlurb(companyData.ir_guidance_blurb || '');
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  useEffect(() => {
    complianceAPI.getJurisdictions().then(setJurisdictions).catch(() => {});
  }, []);

  const handleStartInterview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    try {
      const result = await interviewsApi.create(id, interviewForm);
      setShowInterviewModal(false);
      navigate(`/interview/${result.interview_id}`);
    } catch (err) {
      console.error('Failed to create interview:', err);
    }
  };

  const handleViewTranscript = (interview: Interview) => {
    setSelectedInterview(interview);
    setShowTranscriptModal(true);
  };

  const handleAggregate = async () => {
    if (!id) return;
    setAggregating(true);
    try {
      await companiesApi.aggregateCulture(id);
      fetchData();
    } catch (err) {
      console.error('Failed to aggregate:', err);
    } finally {
      setAggregating(false);
    }
  };

  const handleRunMatching = async () => {
    if (!id) return;
    setMatching(true);
    try {
      await matchingApi.run(id);
      fetchData();
    } catch (err) {
      console.error('Failed to run matching:', err);
    } finally {
      setMatching(false);
    }
  };

  const handleCreatePosition = async (data: Parameters<typeof positionsApi.create>[0]) => {
    setCreatingPosition(true);
    try {
      await positionsApi.create(data);
      setShowPositionModal(false);
      fetchData();
    } catch (err) {
      console.error('Failed to create position:', err);
    } finally {
      setCreatingPosition(false);
    }
  };

  const handleSaveIRGuidance = async () => {
    if (!id) return;
    setSavingIRGuidance(true);
    try {
      const updated = await companiesApi.update(id, { ir_guidance_blurb: irGuidanceBlurb });
      setCompany(updated);
      setEditingIRGuidance(false);
    } catch (err) {
      console.error('Failed to save IR guidance:', err);
    } finally {
      setSavingIRGuidance(false);
    }
  };

  const handleSubmitShop = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !shopForm.city || !shopForm.state) return;
    setShopSaving(true);
    try {
      const data: LocationCreate = {
        name: shopForm.name || undefined,
        address: shopForm.address || undefined,
        city: shopForm.city,
        state: shopForm.state,
        county: shopForm.county || undefined,
        zipcode: shopForm.zipcode || undefined,
      };
      if (editingShop) {
        await complianceAPI.updateLocation(editingShop.id, data, id);
      } else {
        await complianceAPI.createLocation(data, id);
      }
      setShowShopModal(false);
      setEditingShop(null);
      setShopForm(emptyShopForm);
      setUseManualEntry(false);
      setJurisdictionSearch('');
      const updated = await complianceAPI.getLocations(id);
      setShops(updated);
    } catch (err) {
      console.error('Failed to save shop:', err);
    } finally {
      setShopSaving(false);
    }
  };

  const handleDeleteShop = async (shopId: string) => {
    if (!id || !confirm('Delete this shop?')) return;
    try {
      await complianceAPI.deleteLocation(shopId, id);
      setShops(prev => prev.filter(s => s.id !== shopId));
    } catch (err) {
      console.error('Failed to delete shop:', err);
    }
  };

  const openEditShop = (shop: BusinessLocation) => {
    setEditingShop(shop);
    setShopForm({
      name: shop.name || '',
      address: shop.address || '',
      city: shop.city,
      state: shop.state,
      county: shop.county || '',
      zipcode: shop.zipcode,
      jurisdictionKey: `${shop.city}|${shop.state}|${shop.county || ''}`,
    });
    setUseManualEntry(true);
    setJurisdictionSearch('');
    setShowShopModal(true);
  };

  const showJurisdictionPicker = !editingShop && !useManualEntry;

  if (loading) {
    return <div className="text-center py-12 text-zinc-500">Loading...</div>;
  }

  if (!company) {
    return <div className="text-center py-12 text-zinc-500">Company not found</div>;
  }

  const cultureInterviews = interviews.filter((i) => i.interview_type === 'culture');
  const screeningInterviews = interviews.filter((i) => i.interview_type === 'screening');
  const completedCultureInterviews = cultureInterviews.filter((i) => i.status === 'completed');

  const handleStartScreening = async () => {
    if (!id) return;
    try {
      const result = await interviewsApi.create(id, { interview_type: 'screening' });
      navigate(`/interview/${result.interview_id}`);
    } catch (err) {
      console.error('Failed to create screening interview:', err);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/app')} className="text-zinc-500 hover:text-zinc-300 transition-colors">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">{company.name}</h1>
          <p className="text-zinc-400 mt-1">
            {company.industry} {company.size && <span className="text-zinc-600 mx-2">•</span>} {company.size}
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Interviews Section */}
        <Card>
          <CardHeader className="flex justify-between items-center border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">Culture Interviews</h2>
            <Button size="sm" onClick={() => setShowInterviewModal(true)}>
              New Interview
            </Button>
          </CardHeader>
          <CardContent>
            {cultureInterviews.length === 0 ? (
              <p className="text-zinc-500 text-center py-8">No culture interviews yet</p>
            ) : (
              <div className="space-y-3 mt-2">
                {cultureInterviews.map((interview) => (
                  <div
                    key={interview.id}
                    onClick={() => handleViewTranscript(interview)}
                    className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg border border-zinc-800/50 hover:border-zinc-600 cursor-pointer transition-colors"
                  >
                    <div>
                      <p className="font-medium text-zinc-200">
                        {interview.interviewer_name || 'Anonymous'}
                      </p>
                      <p className="text-sm text-zinc-500">
                        {interview.interviewer_role || 'Unknown role'}
                      </p>
                    </div>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                        interview.status === 'completed'
                          ? 'bg-zinc-800 text-white border-zinc-700'
                          : interview.status === 'in_progress'
                          ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
                          : 'bg-zinc-700/50 text-zinc-400 border-zinc-700'
                      }`}
                    >
                      {interview.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {completedCultureInterviews.length > 0 && (
              <div className="mt-6 pt-4 border-t border-zinc-800">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleAggregate}
                  disabled={aggregating}
                  className="w-full"
                >
                  {aggregating ? 'Aggregating...' : 'Aggregate Culture Profile'}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Culture Profile Section */}
        <Card>
          <CardHeader className="border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">Culture Profile</h2>
          </CardHeader>
          <CardContent>
            {company.culture_profile ? (
              <div className="space-y-6 mt-2">
                <p className="text-zinc-300 leading-relaxed">{company.culture_profile.culture_summary}</p>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Collaboration</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.collaboration_style}</span>
                  </div>
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Pace</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.pace}</span>
                  </div>
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Hierarchy</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.hierarchy}</span>
                  </div>
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Remote</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.remote_policy}</span>
                  </div>
                </div>
                {company.culture_profile.values.length > 0 && (
                  <div>
                    <span className="text-sm text-zinc-500 block mb-2">Values</span>
                    <div className="flex flex-wrap gap-2">
                      {company.culture_profile.values.map((value) => (
                        <span
                          key={value}
                          className="px-2.5 py-1 bg-zinc-800 text-white border border-zinc-700 rounded-md text-xs font-medium"
                        >
                          {value}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-zinc-500 text-center py-8">
                Complete interviews and aggregate to build culture profile
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* IR Guidance Section - only show if IR feature is enabled */}
      {hasFeature('incidents') && (
        <Card>
          <CardHeader className="flex justify-between items-center border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">IR Recommendations Guidance</h2>
            {!editingIRGuidance && (
              <Button size="sm" variant="secondary" onClick={() => setEditingIRGuidance(true)}>
                Edit
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {editingIRGuidance ? (
              <div className="space-y-4">
                <textarea
                  value={irGuidanceBlurb}
                  onChange={(e) => setIrGuidanceBlurb(e.target.value)}
                  placeholder="Enter custom guidance for IR recommendations (e.g., company policies, escalation preferences, cultural values to consider)..."
                  rows={4}
                  className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-white focus:border-transparent text-zinc-100 outline-none transition-all resize-none"
                />
                <p className="text-xs text-zinc-500">
                  This guidance will be included when AI generates corrective action recommendations for incidents.
                  Examples: "Prioritize employee wellbeing. Always recommend counseling resources for behavioral incidents."
                </p>
                <div className="flex justify-end gap-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setIrGuidanceBlurb(company?.ir_guidance_blurb || '');
                      setEditingIRGuidance(false);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button size="sm" onClick={handleSaveIRGuidance} disabled={savingIRGuidance}>
                    {savingIRGuidance ? 'Saving...' : 'Save'}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-2">
                {company?.ir_guidance_blurb ? (
                  <p className="text-zinc-300 leading-relaxed whitespace-pre-wrap">{company.ir_guidance_blurb}</p>
                ) : (
                  <p className="text-zinc-500 text-center py-4">
                    No custom IR guidance set. Add guidance to customize AI recommendations for your company.
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Screening Interviews Section */}
      <Card>
        <CardHeader className="flex justify-between items-center border-zinc-800">
          <h2 className="text-lg font-semibold text-zinc-100">Screening Interviews</h2>
          <Button size="sm" onClick={handleStartScreening} className="bg-orange-500 hover:bg-orange-600">
            New Screening
          </Button>
        </CardHeader>
        <CardContent>
          {screeningInterviews.length === 0 ? (
            <p className="text-zinc-500 text-center py-8">
              No screening interviews yet. Screen candidates to assess communication and professionalism.
            </p>
          ) : (
            <div className="space-y-3 mt-2">
              {screeningInterviews.map((interview) => {
                const score = interview.screening_analysis?.overall_score;
                const recommendation = interview.screening_analysis?.recommendation;
                return (
                  <div
                    key={interview.id}
                    onClick={() => navigate(`/app/analysis/${interview.id}`)}
                    className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg border border-zinc-800/50 hover:border-orange-500/50 cursor-pointer transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-zinc-200">
                          Screening #{screeningInterviews.indexOf(interview) + 1}
                        </p>
                        <span className="text-xs text-zinc-500">
                          {new Date(interview.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      {interview.screening_analysis?.summary && (
                        <p className="text-sm text-zinc-400 mt-1 line-clamp-1">
                          {interview.screening_analysis.summary}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {interview.status === 'completed' && score !== undefined ? (
                        <>
                          <span className={`text-xl font-bold ${
                            score >= 80 ? 'text-white' :
                            score >= 60 ? 'text-yellow-400' :
                            score >= 40 ? 'text-orange-400' : 'text-red-400'
                          }`}>
                            {score}
                          </span>
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            recommendation === 'strong_pass' ? 'bg-matcha-500/20 text-white' :
                            recommendation === 'pass' ? 'bg-yellow-500/20 text-yellow-400' :
                            recommendation === 'borderline' ? 'bg-orange-500/20 text-orange-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {recommendation?.replace('_', ' ').toUpperCase()}
                          </span>
                        </>
                      ) : (
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                            interview.status === 'in_progress'
                              ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
                              : 'bg-zinc-700/50 text-zinc-400 border-zinc-700'
                          }`}
                        >
                          {interview.status}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Positions Section */}
      <Card>
        <CardHeader className="flex justify-between items-center border-zinc-800">
          <h2 className="text-lg font-semibold text-zinc-100">Open Positions</h2>
          <Button size="sm" onClick={() => setShowPositionModal(true)}>
            Add Position
          </Button>
        </CardHeader>
        <CardContent>
          {positions.length === 0 ? (
            <p className="text-zinc-500 text-center py-8">
              No positions yet. Add your first position to start matching candidates.
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 mt-2">
              {positions.map((position) => (
                <PositionCard
                  key={position.id}
                  position={position}
                  showCompany={false}
                  onClick={() => navigate(`/positions/${position.id}`)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Shops Section */}
      <Card>
        <CardHeader className="flex justify-between items-center border-zinc-800">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-zinc-100">Shops</h2>
            <span className="text-xs text-zinc-500 font-mono">{shops.length} location{shops.length !== 1 ? 's' : ''}</span>
          </div>
          <Button size="sm" onClick={() => {
            setShopForm(emptyShopForm);
            setEditingShop(null);
            setUseManualEntry(false);
            setJurisdictionSearch('');
            setShowShopModal(true);
          }}>
            <Plus size={14} className="mr-1" />
            Add Shop
          </Button>
        </CardHeader>
        <CardContent>
          {shops.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-800/50 border border-zinc-700 flex items-center justify-center">
                <MapPin size={20} className="text-zinc-500" />
              </div>
              <p className="text-zinc-500 text-sm mb-3">No shops yet</p>
              <button
                onClick={() => {
                  setShopForm(emptyShopForm);
                  setEditingShop(null);
                  setUseManualEntry(false);
                  setJurisdictionSearch('');
                  setShowShopModal(true);
                }}
                className="text-white text-xs font-bold hover:text-zinc-300 uppercase tracking-wider underline underline-offset-4"
              >
                Add your first shop
              </button>
            </div>
          ) : (
            <div className="space-y-2 mt-2">
              {shops.map(shop => (
                <div
                  key={shop.id}
                  className="flex items-center justify-between p-4 bg-zinc-800/30 rounded-lg border border-zinc-800/50 hover:border-zinc-700 transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="w-9 h-9 bg-zinc-800 border border-zinc-700 rounded flex items-center justify-center shrink-0">
                      <MapPin size={16} className="text-zinc-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-zinc-200 truncate">
                        {shop.name || `${shop.city}, ${shop.state}`}
                      </p>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-xs text-zinc-500 font-mono truncate">
                          {shop.address ? `${shop.address}, ` : ''}{shop.city}, {shop.state} {shop.zipcode}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 mt-1.5 text-[10px] uppercase tracking-wider">
                        <span className="text-zinc-500 flex items-center gap-1">
                          <Shield size={10} />
                          {shop.requirements_count} reqs
                        </span>
                        {shop.last_compliance_check && (
                          <span className="text-zinc-600">
                            Checked {new Date(shop.last_compliance_check).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEditShop(shop)}
                      className="p-1.5 text-zinc-500 hover:text-white rounded transition-colors"
                      title="Edit"
                    >
                      <Edit2 size={13} />
                    </button>
                    <button
                      onClick={() => handleDeleteShop(shop.id)}
                      className="p-1.5 text-zinc-500 hover:text-red-400 rounded transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Matches Section */}
      {company.culture_profile && (
        <Card>
          <CardHeader className="flex justify-between items-center border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">Candidate Matches</h2>
            <Button size="sm" onClick={handleRunMatching} disabled={matching}>
              {matching ? 'Matching...' : 'Run Matching'}
            </Button>
          </CardHeader>
          <CardContent>
            {matches.length === 0 ? (
              <p className="text-zinc-500 text-center py-8">
                No matches yet. Upload candidates and run matching.
              </p>
            ) : (
              <div className="space-y-4 mt-2">
                {matches.map((match) => (
                  <div
                    key={match.id}
                    className="flex items-center justify-between p-4 bg-zinc-800/30 rounded-lg border border-zinc-800/50 hover:border-zinc-700 transition-colors"
                  >
                    <div className="flex-1 pr-4">
                      <p className="font-medium text-zinc-200 text-lg mb-1">{match.candidate_name || 'Unknown'}</p>
                      <p className="text-sm text-zinc-400 line-clamp-2 leading-relaxed">
                        {match.match_reasoning}
                      </p>
                    </div>
                    <div className="ml-4 text-center min-w-[80px]">
                      <div
                        className={`text-3xl font-bold ${
                          match.match_score >= 80
                            ? 'text-white'
                            : match.match_score >= 60
                            ? 'text-yellow-400'
                            : 'text-red-400'
                        }`}
                      >
                        {Math.round(match.match_score)}
                      </div>
                      <div className="text-xs text-zinc-500 mt-1 uppercase tracking-wide font-medium">Match Score</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Interview Modal */}
      <Modal
        isOpen={showInterviewModal}
        onClose={() => setShowInterviewModal(false)}
        title="Start Culture Interview"
      >
        <form onSubmit={handleStartInterview} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">
              Interviewer Name
            </label>
            <input
              type="text"
              value={interviewForm.interviewer_name}
              onChange={(e) =>
                setInterviewForm({ ...interviewForm, interviewer_name: e.target.value })
              }
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-white focus:border-transparent text-zinc-100 outline-none transition-all"
              placeholder="John Smith"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">Role</label>
            <input
              type="text"
              value={interviewForm.interviewer_role}
              onChange={(e) =>
                setInterviewForm({ ...interviewForm, interviewer_role: e.target.value })
              }
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-white focus:border-transparent text-zinc-100 outline-none transition-all"
              placeholder="VP of Engineering"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800 mt-6">
            <Button type="button" variant="secondary" onClick={() => setShowInterviewModal(false)}>
              Cancel
            </Button>
            <Button type="submit">Start Interview</Button>
          </div>
        </form>
      </Modal>

      {/* Transcript Modal */}
      <Modal
        isOpen={showTranscriptModal}
        onClose={() => setShowTranscriptModal(false)}
        title={`Interview: ${selectedInterview?.interviewer_name}`}
      >
        <div className="space-y-6 max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar">
          <div>
            <h4 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-2">Transcript</h4>
            {selectedInterview?.transcript ? (
              <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-800">
                <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {selectedInterview.transcript}
                </pre>
              </div>
            ) : (
              <p className="text-zinc-500 text-sm italic">No transcript available for this session.</p>
            )}
          </div>

          {selectedInterview?.raw_culture_data && (
            <div>
              <h4 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-2">Extracted Culture Data</h4>
              <div className="bg-zinc-800/30 rounded-lg p-4 border border-zinc-800">
                <pre className="text-xs text-white overflow-x-auto">
                  {JSON.stringify(selectedInterview.raw_culture_data, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
        <div className="flex justify-end mt-6 pt-4 border-t border-zinc-800">
          <Button onClick={() => setShowTranscriptModal(false)} variant="secondary">
            Close
          </Button>
        </div>
      </Modal>

      {/* Position Modal */}
      <Modal
        isOpen={showPositionModal}
        onClose={() => setShowPositionModal(false)}
        title="Add New Position"
      >
        <PositionForm
          companies={company ? [company] : []}
          initialCompanyId={id}
          onSubmit={handleCreatePosition}
          onCancel={() => setShowPositionModal(false)}
          isLoading={creatingPosition}
        />
      </Modal>

      {/* Shop Modal */}
      <Modal
        isOpen={showShopModal}
        onClose={() => {
          setShowShopModal(false);
          setEditingShop(null);
          setShopForm(emptyShopForm);
          setJurisdictionSearch('');
          setUseManualEntry(false);
        }}
        title={editingShop ? 'Edit Shop' : 'Add Shop'}
      >
        <form onSubmit={handleSubmitShop} className="space-y-4">
          <div>
            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
              Shop Name (optional)
            </label>
            <input
              type="text"
              value={shopForm.name}
              onChange={e => setShopForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g., Main Office, Warehouse"
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
            />
          </div>

          {showJurisdictionPicker ? (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500">
                  Jurisdiction <span className="text-red-500">*</span>
                </label>
                <button
                  type="button"
                  onClick={() => { setUseManualEntry(true); setShopForm(prev => ({ ...prev, jurisdictionKey: '' })); }}
                  className="text-[10px] text-zinc-600 hover:text-zinc-400 uppercase tracking-wider transition-colors"
                >
                  Enter manually
                </button>
              </div>
              <input
                type="text"
                value={jurisdictionSearch}
                onChange={e => setJurisdictionSearch(e.target.value)}
                placeholder="Search by city or state..."
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700 mb-2"
              />
              <div className="max-h-48 overflow-y-auto border border-zinc-800 rounded-lg bg-zinc-900">
                {Object.keys(filteredJurisdictions).length === 0 ? (
                  <div className="px-3 py-4 text-center text-zinc-600 text-xs">
                    {jurisdictionSearch ? 'No matching jurisdictions' : 'Loading jurisdictions...'}
                  </div>
                ) : (
                  Object.entries(filteredJurisdictions).map(([state, items]) => {
                    const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
                    return (
                      <div key={state}>
                        <div className="px-3 py-1.5 bg-zinc-950 text-[10px] text-zinc-500 font-bold uppercase tracking-wider sticky top-0">
                          {stateLabel}
                        </div>
                        {items.map(j => {
                          const key = makeJurisdictionKey(j);
                          const isSelected = shopForm.jurisdictionKey === key;
                          return (
                            <button
                              key={key}
                              type="button"
                              onClick={() => {
                                setShopForm(prev => ({
                                  ...prev,
                                  city: j.city,
                                  state: j.state,
                                  county: j.county || '',
                                  jurisdictionKey: key,
                                }));
                              }}
                              className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center justify-between ${
                                isSelected
                                  ? 'bg-white/10 text-white'
                                  : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                              }`}
                            >
                              <span>{j.city}, {j.state}</span>
                              {j.has_local_ordinance && (
                                <span className="text-[9px] px-1.5 py-0.5 bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 rounded uppercase tracking-wider font-bold">
                                  Local
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    );
                  })
                )}
              </div>
              {shopForm.jurisdictionKey && (
                <div className="mt-2 px-3 py-2 bg-zinc-800/50 border border-zinc-700 rounded-lg text-xs text-zinc-300">
                  Selected: <span className="text-white font-bold">{shopForm.city}, {shopForm.state}</span>
                  {shopForm.county && <span className="text-zinc-500 ml-1">({shopForm.county} County)</span>}
                </div>
              )}
            </div>
          ) : (
            <>
              {!editingShop && useManualEntry && (
                <button
                  type="button"
                  onClick={() => { setUseManualEntry(false); setShopForm(emptyShopForm); }}
                  className="text-[10px] text-zinc-600 hover:text-zinc-400 uppercase tracking-wider transition-colors"
                >
                  Use jurisdiction picker
                </button>
              )}
              <div>
                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                  Street Address (optional)
                </label>
                <input
                  type="text"
                  value={shopForm.address}
                  onChange={e => setShopForm(prev => ({ ...prev, address: e.target.value }))}
                  placeholder="123 Main St"
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                    City <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={shopForm.city}
                    onChange={e => setShopForm(prev => ({ ...prev, city: e.target.value }))}
                    required
                    placeholder="San Francisco"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                  />
                </div>
                <div>
                  <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                    State <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={shopForm.state}
                    onChange={e => setShopForm(prev => ({ ...prev, state: e.target.value }))}
                    required
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors"
                  >
                    <option value="">Select...</option>
                    {US_STATES.map(state => (
                      <option key={state.value} value={state.value}>{state.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                    County (optional)
                  </label>
                  <input
                    type="text"
                    value={shopForm.county}
                    onChange={e => setShopForm(prev => ({ ...prev, county: e.target.value }))}
                    placeholder="San Francisco"
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                  />
                </div>
                <div>
                  <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                    ZIP Code
                  </label>
                  <input
                    type="text"
                    value={shopForm.zipcode}
                    onChange={e => setShopForm(prev => ({ ...prev, zipcode: e.target.value }))}
                    placeholder="94105"
                    maxLength={10}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm rounded-lg focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                  />
                </div>
              </div>
            </>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800 mt-6">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setShowShopModal(false);
                setEditingShop(null);
                setShopForm(emptyShopForm);
                setJurisdictionSearch('');
                setUseManualEntry(false);
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={shopSaving || (showJurisdictionPicker && !shopForm.jurisdictionKey)}
            >
              {shopSaving ? 'Saving...' : editingShop ? 'Update Shop' : 'Add Shop'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default CompanyDetail;
