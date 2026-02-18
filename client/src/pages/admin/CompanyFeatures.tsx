import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminCompanyFeatures } from '../../api/client';
import type { CompanyWithFeatures, EnabledFeatures } from '../../types';
import { Building2 } from 'lucide-react';

const FEATURE_CONFIG: { key: string; label: string; section: string }[] = [
  { key: 'offer_letters', label: 'Offer Letters', section: 'Recruiting' },
  { key: 'policies', label: 'Policies', section: 'Recruiting' },
  { key: 'handbooks', label: 'Handbooks', section: 'Recruiting' },
  { key: 'compliance', label: 'Compliance', section: 'Recruiting' },
  { key: 'compliance_plus', label: 'Compliance Plus', section: 'HR Tools' },
  { key: 'employees', label: 'Employees', section: 'Recruiting' },
  { key: 'vibe_checks', label: 'Vibe Checks', section: 'Employee Experience' },
  { key: 'enps', label: 'eNPS Surveys', section: 'Employee Experience' },
  { key: 'performance_reviews', label: 'Performance Reviews', section: 'Employee Experience' },
  { key: 'er_copilot', label: 'ER Copilot', section: 'HR Tools' },
  { key: 'incidents', label: 'Incidents', section: 'HR Tools' },
  { key: 'time_off', label: 'Time Off', section: 'HR Tools' },
  { key: 'accommodations', label: 'Accommodations', section: 'HR Tools' },
  { key: 'interview_prep', label: 'Tutor', section: 'HR Tools' },
];

export function CompanyFeatures() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState<CompanyWithFeatures[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  const fetchCompanies = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await adminCompanyFeatures.list();
      setCompanies(data);
    } catch (err) {
      console.error('Failed to fetch companies:', err);
      setError('Failed to load company features');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCompanies();
  }, [fetchCompanies]);

  const handleToggle = async (companyId: string, feature: string, currentValue: boolean) => {
    const toggleKey = `${companyId}-${feature}`;
    setToggling(toggleKey);
    try {
      const result = await adminCompanyFeatures.toggle(companyId, feature, !currentValue);
      setCompanies(prev =>
        prev.map(c =>
          c.id === companyId
            ? { ...c, enabled_features: result.enabled_features }
            : c
        )
      );
    } catch (err) {
      console.error('Failed to toggle feature:', err);
      setError('Failed to update feature');
    } finally {
      setToggling(null);
    }
  };

  const enableAll = async (companyId: string) => {
    for (const feat of FEATURE_CONFIG) {
      const company = companies.find(c => c.id === companyId);
      if (company && !company.enabled_features[feat.key]) {
        await handleToggle(companyId, feat.key, false);
      }
    }
  };

  const disableAll = async (companyId: string) => {
    for (const feat of FEATURE_CONFIG) {
      const company = companies.find(c => c.id === companyId);
      if (company && company.enabled_features[feat.key]) {
        await handleToggle(companyId, feat.key, true);
      }
    }
  };

  const getEnabledCount = (features: EnabledFeatures) => {
    return FEATURE_CONFIG.filter(f => features[f.key]).length;
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-3 border-b border-white/10 pb-6 md:pb-8">
        <div>
          <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">Company Features</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Toggle features on/off per company
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 font-mono">
            {companies.length} Companies
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Main Content */}
      <div className="border border-white/10 bg-zinc-900/30">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading companies...</div>
          </div>
        ) : companies.length === 0 ? (
          <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
            No companies found
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden lg:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10 bg-zinc-950">
                    <th className="text-left px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest sticky left-0 bg-zinc-950 z-10">
                      Company
                    </th>
                    {FEATURE_CONFIG.map(feat => (
                      <th
                        key={feat.key}
                        className="text-center px-2 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest min-w-[80px]"
                      >
                        <div className="flex flex-col items-center gap-1">
                          <span className="text-[8px] text-zinc-600">{feat.section}</span>
                          <span>{feat.label}</span>
                        </div>
                      </th>
                    ))}
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {companies.map((company) => (
                    <tr
                      key={company.id}
                      className="border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950"
                    >
                      <td className="px-6 py-4 sticky left-0 bg-zinc-950 z-10">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center flex-shrink-0">
                            <Building2 size={14} className="text-zinc-400" />
                          </div>
                          <div>
                            <div className="text-sm text-white font-bold">{company.company_name}</div>
                            <div className="flex items-center gap-2 mt-0.5">
                              {company.industry && (
                                <span className="text-[10px] text-zinc-500 font-mono">{company.industry}</span>
                              )}
                              <span className={`text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${
                                company.status === 'approved'
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                  : company.status === 'pending'
                                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                  : 'bg-red-500/10 text-red-400 border-red-500/20'
                              }`}>
                                {company.status}
                              </span>
                              <span className="text-[10px] text-zinc-600 font-mono">
                                {getEnabledCount(company.enabled_features)}/{FEATURE_CONFIG.length}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>
                      {FEATURE_CONFIG.map(feat => {
                        const enabled = company.enabled_features[feat.key] ?? false;
                        const isToggling = toggling === `${company.id}-${feat.key}`;
                        return (
                          <td key={feat.key} className="text-center px-2 py-4">
                            <button
                              onClick={() => handleToggle(company.id, feat.key, enabled)}
                              disabled={isToggling}
                              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                                enabled ? 'bg-emerald-500' : 'bg-zinc-700'
                              } ${isToggling ? 'opacity-50' : ''}`}
                            >
                              <span
                                className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                                  enabled ? 'translate-x-[18px]' : 'translate-x-[3px]'
                                }`}
                              />
                            </button>
                          </td>
                        );
                      })}
                      <td className="text-center px-4 py-4">
                        <div className="flex flex-col items-center justify-center gap-1">
                          <button
                            onClick={() => navigate(`/app/admin/candidate-metrics?company_id=${company.id}`)}
                            className="text-[9px] px-2 py-1 text-emerald-400 hover:text-emerald-300 border border-emerald-500/20 hover:border-emerald-500/40 transition-colors uppercase tracking-wider mb-1 w-full"
                          >
                            Metrics
                          </button>
                          <div className="flex gap-1 w-full">
                            <button
                              onClick={() => enableAll(company.id)}
                              className="flex-1 text-[9px] px-2 py-1 text-zinc-500 hover:text-emerald-400 border border-zinc-800 hover:border-emerald-500/30 transition-colors uppercase tracking-wider"
                            >
                              All
                            </button>
                            <button
                              onClick={() => disableAll(company.id)}
                              className="flex-1 text-[9px] px-2 py-1 text-zinc-500 hover:text-red-400 border border-zinc-800 hover:border-red-500/30 transition-colors uppercase tracking-wider"
                            >
                              None
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile/tablet card layout */}
            <div className="lg:hidden divide-y divide-white/5">
              {companies.map((company) => (
                <div key={company.id} className="p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                        <Building2 size={14} className="text-zinc-400" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm text-white font-bold truncate">{company.company_name}</div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${
                            company.status === 'approved'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : company.status === 'pending'
                              ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                              : 'bg-red-500/10 text-red-400 border-red-500/20'
                          }`}>
                            {company.status}
                          </span>
                          <span className="text-[10px] text-zinc-600 font-mono">
                            {getEnabledCount(company.enabled_features)}/{FEATURE_CONFIG.length}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => navigate(`/app/admin/candidate-metrics?company_id=${company.id}`)}
                        className="text-[9px] px-2 py-1 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider"
                      >
                        Metrics
                      </button>
                      <button
                        onClick={() => enableAll(company.id)}
                        className="text-[9px] px-2 py-1 text-zinc-500 hover:text-emerald-400 border border-zinc-800 hover:border-emerald-500/30 transition-colors uppercase tracking-wider"
                      >
                        All
                      </button>
                      <button
                        onClick={() => disableAll(company.id)}
                        className="text-[9px] px-2 py-1 text-zinc-500 hover:text-red-400 border border-zinc-800 hover:border-red-500/30 transition-colors uppercase tracking-wider"
                      >
                        None
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 xs:grid-cols-2 sm:grid-cols-3 gap-2">
                    {FEATURE_CONFIG.map(feat => {
                      const enabled = company.enabled_features[feat.key] ?? false;
                      const isToggling = toggling === `${company.id}-${feat.key}`;
                      return (
                        <button
                          key={feat.key}
                          onClick={() => handleToggle(company.id, feat.key, enabled)}
                          disabled={isToggling}
                          className={`flex items-center justify-between gap-3 px-3 py-2.5 border transition-all active:scale-[0.98] ${
                            enabled
                              ? 'bg-emerald-500/10 border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.05)]'
                              : 'bg-zinc-900/50 border-zinc-800 hover:border-zinc-700'
                          } ${isToggling ? 'opacity-50' : ''}`}
                        >
                          <div className="min-w-0 flex flex-col items-start">
                            <span className="text-[7px] text-zinc-600 uppercase tracking-widest leading-none mb-1">{feat.section}</span>
                            <span className={`text-[10px] font-bold uppercase tracking-wider truncate w-full text-left ${enabled ? 'text-emerald-400' : 'text-zinc-500'}`}>
                              {feat.label}
                            </span>
                          </div>
                          <div className={`relative inline-flex h-4 w-7 items-center rounded-full shrink-0 transition-colors ${
                            enabled ? 'bg-emerald-500' : 'bg-zinc-700'
                          }`}>
                            <span className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${
                              enabled ? 'translate-x-[13px]' : 'translate-x-[2px]'
                            }`} />
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default CompanyFeatures;
