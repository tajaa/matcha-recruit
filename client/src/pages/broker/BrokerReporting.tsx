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
  const [agreedToTerms, setAgreedToTerms] = useState(false);
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
    if (!brokerProfile || !agreedToTerms) return;
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
        <div data-tour="broker-reporting-terms" className="border border-amber-600/40 bg-amber-950/20 p-6 rounded-sm">
          <h3 className="text-lg font-medium text-amber-500 mb-2">Partner Terms & Conditions</h3>
          <div className="text-sm text-zinc-300 space-y-3 mb-6">
            <p>To access broker portfolio reporting and participate in the partner program, you must agree to our Broker Partner Terms:</p>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>10% Commission:</strong> Recurring commission on base subscription fees for referred teams.</li>
              <li><strong>No Liability:</strong> Matcha is not liable for service issues or compliance outcomes.</li>
              <li><strong>Independent Relationship:</strong> We operate as independent contractors.</li>
            </ul>
            <p>
              Please review the{' '}
              <a href="/app/broker/terms" target="_blank" rel="noopener noreferrer" className="text-amber-500 underline underline-offset-4 hover:text-amber-400">
                full Partner Terms
              </a>{' '}
              for complete details.
            </p>
          </div>

          <div className="flex items-start gap-3 mb-6">
            <input
              id="terms-checkbox"
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              className="mt-1 w-4 h-4 bg-zinc-900 border-zinc-700 text-amber-500 focus:ring-amber-500 focus:ring-offset-zinc-950 rounded-sm"
            />
            <label htmlFor="terms-checkbox" className="text-sm text-zinc-300 cursor-pointer select-none">
              I have read and agree to the Broker Partner Terms, including the referral commission structure and liability disclaimers.
            </label>
          </div>

          <button
            onClick={handleAcceptTerms}
            disabled={acceptingTerms || !agreedToTerms}
            className="px-6 py-2 text-xs uppercase tracking-widest font-bold bg-amber-500 text-black hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {acceptingTerms ? 'Recording Acceptance...' : 'Accept & Unlock Reporting'}
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
