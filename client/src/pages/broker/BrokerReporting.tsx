import { useEffect, useState } from 'react';
import { auth, brokerPortal } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { FeatureGuideTrigger } from '../../features/feature-guides';
import type { BrokerAuthProfile, BrokerPortfolioReportResponse } from '../../types';

function asBrokerProfile(profile: unknown): BrokerAuthProfile | null {
  if (!profile || typeof profile !== 'object') return null;
  if (!('broker_id' in profile)) return null;
  return profile as BrokerAuthProfile;
}

export default function BrokerReporting() {
  const { profile, refreshUser } = useAuth();
  const brokerProfile = asBrokerProfile(profile);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [acceptingTerms, setAcceptingTerms] = useState(false);
  const [report, setReport] = useState<BrokerPortfolioReportResponse | null>(null);

  const loadReport = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await brokerPortal.getPortfolioReport();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load broker reporting');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  const handleAcceptTerms = async () => {
    if (!brokerProfile) return;
    setAcceptingTerms(true);
    setError('');
    try {
      await auth.acceptBrokerTerms(brokerProfile.terms_required_version);
      await refreshUser();
      await loadReport();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept broker terms');
    } finally {
      setAcceptingTerms(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-white">Broker Portfolio Reporting</h1>
          <FeatureGuideTrigger guideId="broker-reporting" />
        </div>
        <p className="text-sm text-zinc-400">Aggregated, redacted compliance and adoption reporting across your client book.</p>
      </div>

      {!brokerProfile?.terms_accepted && (
        <div data-tour="broker-reporting-terms" className="border border-amber-600/40 bg-amber-950/20 p-4 rounded-sm">
          <p className="text-sm text-amber-200 mb-3">
            Accept broker partner terms ({brokerProfile?.terms_required_version || 'v1'}) to unlock reporting.
          </p>
          <button
            onClick={handleAcceptTerms}
            disabled={acceptingTerms}
            className="px-3 py-2 text-xs uppercase tracking-wide bg-amber-500 text-black disabled:opacity-60"
          >
            {acceptingTerms ? 'Accepting...' : 'Accept Terms'}
          </button>
        </div>
      )}

      {error && <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">{error}</div>}

      {loading ? (
        <div className="text-sm text-zinc-400">Loading reporting...</div>
      ) : !report ? (
        <div className="text-sm text-zinc-400">No report available.</div>
      ) : (
        <>
          <div data-tour="broker-reporting-summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-zinc-900 border border-zinc-800 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Linked Companies</p>
              <p className="text-lg text-white">{report.summary.total_linked_companies}</p>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Active Links</p>
              <p className="text-lg text-white">{report.summary.active_link_count}</p>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Avg Compliance</p>
              <p className="text-lg text-white">{report.summary.average_policy_compliance_rate}%</p>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Open Action Items</p>
              <p className="text-lg text-white">{report.summary.open_action_item_total}</p>
            </div>
          </div>

          <div data-tour="broker-reporting-redaction" className="bg-zinc-900 border border-zinc-800 p-4">
            <p className="text-xs text-zinc-400">{report.redaction.note}</p>
          </div>

          <div data-tour="broker-reporting-signals" className="bg-zinc-900 border border-zinc-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-zinc-800 text-sm uppercase tracking-wide text-zinc-300">Company Signals</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-zinc-950 text-zinc-400">
                  <tr>
                    <th className="text-left p-3 font-medium">Company</th>
                    <th className="text-left p-3 font-medium">Link</th>
                    <th className="text-left p-3 font-medium">Compliance</th>
                    <th className="text-left p-3 font-medium">Open Items</th>
                    <th className="text-left p-3 font-medium">Employees</th>
                    <th className="text-left p-3 font-medium">Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {report.companies.map((company) => (
                    <tr key={company.company_id}>
                      <td className="p-3 text-white">{company.company_name}</td>
                      <td className="p-3 text-zinc-300">{company.link_status}</td>
                      <td className="p-3 text-zinc-300">{company.policy_compliance_rate}%</td>
                      <td className="p-3 text-zinc-300">{company.open_action_items}</td>
                      <td className="p-3 text-zinc-300">{company.active_employee_count}</td>
                      <td className="p-3">
                        <span
                          className={`px-2 py-1 text-[10px] uppercase tracking-wide border ${
                            company.risk_signal === 'healthy'
                              ? 'border-emerald-700 text-emerald-300'
                              : company.risk_signal === 'at_risk'
                              ? 'border-red-700 text-red-300'
                              : 'border-amber-700 text-amber-300'
                          }`}
                        >
                          {company.risk_signal}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
