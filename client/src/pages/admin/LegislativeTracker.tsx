import { useState, useCallback } from 'react';
import { api } from '../../api/client';
import type { TrackedBill, LegislativeScanResponse } from '../../api/client';
import {
  Scale,
  ExternalLink,
  AlertCircle,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  BarChart2,
  Sparkles,
  Calculator,
} from 'lucide-react';

const DEFAULT_KEYWORDS = [
  'minimum wage',
  'paid leave',
  'paid sick leave',
  'overtime',
  'employee classification',
  'workplace safety',
  'pay transparency',
  'predictive scheduling',
  'non-compete',
  'equal pay',
];

const STATE_OPTIONS = [
  { value: 'ALL', label: 'All States' },
  { value: 'CA', label: 'California' },
  { value: 'NY', label: 'New York' },
  { value: 'TX', label: 'Texas' },
  { value: 'FL', label: 'Florida' },
  { value: 'IL', label: 'Illinois' },
  { value: 'WA', label: 'Washington' },
  { value: 'MA', label: 'Massachusetts' },
  { value: 'CO', label: 'Colorado' },
  { value: 'US', label: 'Congress (Federal)' },
];

type SortKey = 'probability' | 'state' | 'status' | 'last_action_date';

function probabilityColor(p: number): string {
  if (p >= 0.8) return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
  if (p >= 0.6) return 'text-orange-400 bg-orange-500/10 border-orange-500/20';
  if (p >= 0.4) return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
  if (p >= 0.2) return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
  return 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20';
}

function probabilityBarColor(p: number): string {
  if (p >= 0.8) return 'bg-emerald-500';
  if (p >= 0.6) return 'bg-orange-500';
  if (p >= 0.4) return 'bg-amber-500';
  if (p >= 0.2) return 'bg-blue-500';
  return 'bg-zinc-400';
}

function statusColor(status: number): string {
  if (status === 4) return 'text-emerald-400 bg-emerald-500/10';
  if (status === 5) return 'text-red-400 bg-red-500/10';
  if (status === 6) return 'text-zinc-500 bg-zinc-500/10';
  if (status === 3) return 'text-blue-400 bg-blue-500/10';
  if (status === 2) return 'text-violet-400 bg-violet-500/10';
  return 'text-zinc-400 bg-zinc-500/10';
}

function SourceIcon({ source }: { source: TrackedBill['probability_source'] }) {
  if (source === 'polymarket') {
    return (
      <span title="Polymarket prediction market">
        <BarChart2 className="w-3.5 h-3.5 text-blue-500" />
      </span>
    );
  }
  if (source === 'gemini') {
    return (
      <span title="Gemini AI estimate">
        <Sparkles className="w-3.5 h-3.5 text-violet-500" />
      </span>
    );
  }
  return (
    <span title="Stage heuristic">
      <Calculator className="w-3.5 h-3.5 text-zinc-400" />
    </span>
  );
}

function BillRow({ bill }: { bill: TrackedBill }) {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(bill.probability * 100);

  return (
    <>
      <tr
        className="border-b border-white/5 hover:bg-white/5 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-zinc-800 text-zinc-300">
            {bill.state}
          </span>
        </td>
        <td className="px-4 py-3">
          <a
            href={bill.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-mono text-blue-400 hover:underline flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            {bill.bill_number}
            <ExternalLink className="w-3 h-3" />
          </a>
        </td>
        <td className="px-4 py-3 max-w-xs">
          <p className="text-sm text-zinc-300 line-clamp-2">{bill.title}</p>
        </td>
        <td className="px-4 py-3">
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-300 border border-white/10">
            {bill.category}
          </span>
        </td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusColor(bill.status)}`}>
            {bill.status_label}
          </span>
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="w-16 bg-zinc-800 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full ${probabilityBarColor(bill.probability)}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded border ${probabilityColor(bill.probability)}`}>
              {pct}%
            </span>
            <SourceIcon source={bill.probability_source} />
          </div>
        </td>
        <td className="px-4 py-3">
          <div className="text-xs text-zinc-500">
            <div className="font-medium text-zinc-400">{bill.last_action_date}</div>
            <div className="line-clamp-1 mt-0.5">{bill.last_action}</div>
          </div>
        </td>
        <td className="px-4 py-3">
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-zinc-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-zinc-400" />
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-zinc-900/50 border-b border-white/5">
          <td colSpan={8} className="px-6 py-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              {bill.description && (
                <div>
                  <div className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1">Description</div>
                  <p className="text-zinc-300">{bill.description}</p>
                </div>
              )}
              {bill.sponsors && bill.sponsors.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1">
                    Sponsors ({bill.sponsors.length})
                  </div>
                  <ul className="space-y-1">
                    {bill.sponsors.slice(0, 5).map((s, i) => (
                      <li key={i} className="text-zinc-300 flex items-center gap-1.5">
                        <span className={`inline-block w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center ${s.party === 'D' ? 'bg-blue-500/20 text-blue-400' : s.party === 'R' ? 'bg-red-500/20 text-red-400' : 'bg-zinc-700 text-zinc-400'}`}>
                          {s.party || '?'}
                        </span>
                        {s.name}
                        {s.role && <span className="text-zinc-500 text-xs">({s.role})</span>}
                      </li>
                    ))}
                    {bill.sponsors.length > 5 && (
                      <li className="text-zinc-500 text-xs">+{bill.sponsors.length - 5} more</li>
                    )}
                  </ul>
                </div>
              )}
              <div>
                <div className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1">Probability</div>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold px-2 py-0.5 rounded border ${probabilityColor(bill.probability)}`}>
                    {Math.round(bill.probability * 100)}%
                  </span>
                  <span className="text-zinc-500 text-xs capitalize">{bill.probability_source}</span>
                </div>
                {bill.probability_reasoning && (
                  <p className="mt-1 text-zinc-400 text-xs">{bill.probability_reasoning}</p>
                )}
                {bill.polymarket_url && (
                  <a
                    href={bill.polymarket_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 flex items-center gap-1 text-xs text-blue-400 hover:underline"
                  >
                    View on Polymarket
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function LegislativeTracker() {
  const [result, setResult] = useState<LegislativeScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [activeKeywords, setActiveKeywords] = useState<Set<string>>(new Set(DEFAULT_KEYWORDS));
  const [selectedStates, setSelectedStates] = useState<string>('ALL');
  const [sortKey, setSortKey] = useState<SortKey>('probability');
  const [sortAsc, setSortAsc] = useState(false);

  const toggleKeyword = (kw: string) => {
    setActiveKeywords((prev) => {
      const next = new Set(prev);
      if (next.has(kw)) {
        next.delete(kw);
      } else {
        next.add(kw);
      }
      return next;
    });
  };

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key !== 'probability');
    }
  };

  const runScan = useCallback(async () => {
    if (activeKeywords.size === 0) {
      setError('Select at least one keyword to search.');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const kw = Array.from(activeKeywords).join(',');
      const states = selectedStates === 'ALL' ? undefined : selectedStates;
      const data = await api.adminLegislativeTracker.scan({
        keywords: kw,
        states,
      });
      setResult(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scan failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [activeKeywords, selectedStates]);

  const sortedBills = result
    ? [...result.bills].sort((a, b) => {
        let cmp = 0;
        if (sortKey === 'probability') cmp = a.probability - b.probability;
        else if (sortKey === 'state') cmp = a.state.localeCompare(b.state);
        else if (sortKey === 'status') cmp = a.status - b.status;
        else if (sortKey === 'last_action_date')
          cmp = a.last_action_date.localeCompare(b.last_action_date);
        return sortAsc ? cmp : -cmp;
      })
    : [];

  const SortButton = ({ label, sKey }: { label: string; sKey: SortKey }) => (
    <button
      onClick={() => handleSort(sKey)}
      className="flex items-center gap-1 text-xs font-semibold text-zinc-500 uppercase tracking-widest hover:text-zinc-200"
    >
      {label}
      {sortKey === sKey ? (
        sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
      ) : (
        <ChevronDown className="w-3 h-3 opacity-30" />
      )}
    </button>
  );

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-zinc-800 border border-zinc-700/50">
            <Scale className="w-5 h-5 text-zinc-400" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white">Legislative Tracker</h1>
            <p className="text-sm text-zinc-500 mt-0.5">
              Pending HR bills across all 50 states + Congress with passage probability
            </p>
          </div>
        </div>
        <button
          onClick={runScan}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white text-black text-sm font-medium hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <TrendingUp className="w-4 h-4" />
          {loading ? 'Scanning…' : 'Run Scan'}
        </button>
      </div>

      {/* Filter bar */}
      <div className="bg-zinc-900/30 border border-white/10 rounded-xl p-4 mb-6">
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Keywords</div>
            <div className="flex flex-wrap gap-2">
              {DEFAULT_KEYWORDS.map((kw) => (
                <button
                  key={kw}
                  onClick={() => toggleKeyword(kw)}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                    activeKeywords.has(kw)
                      ? 'bg-white text-black border-white'
                      : 'bg-zinc-900 text-zinc-400 border-zinc-700/50 hover:border-zinc-500'
                  }`}
                >
                  {kw}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div>
              <div className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">State Filter</div>
              <select
                value={selectedStates}
                onChange={(e) => setSelectedStates(e.target.value)}
                className="px-3 py-1.5 rounded-lg border border-zinc-700 text-sm text-zinc-300 bg-zinc-900 focus:outline-none focus:border-zinc-500"
              >
                {STATE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500 sm:mt-5">
              <span className="flex items-center gap-1">
                <BarChart2 className="w-3.5 h-3.5 text-blue-500" /> Polymarket
              </span>
              <span className="flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-violet-500" /> Gemini AI
              </span>
              <span className="flex items-center gap-1">
                <Calculator className="w-3.5 h-3.5 text-zinc-400" /> Heuristic
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 text-sm text-red-400">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="bg-zinc-900/30 border border-white/10 rounded-xl p-8 text-center">
          <div className="inline-flex items-center gap-3 text-zinc-400">
            <div className="w-5 h-5 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm">
              Scanning {selectedStates === 'ALL' ? '51 jurisdictions' : selectedStates} for {activeKeywords.size} keyword{activeKeywords.size !== 1 ? 's' : ''}…
            </span>
          </div>
          <p className="text-xs text-zinc-500 mt-2">Searching via Gemini — may take 15–30 seconds</p>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-zinc-400">
              <span className="font-semibold text-zinc-200">{result.total}</span> bills found
              {' · '}
              <span className="text-blue-400">{result.polymarket_matches} Polymarket</span>
              {' · '}
              <span className="text-violet-400">{result.gemini_estimates} Gemini</span>
              {' · '}
              <span className="text-zinc-500">{result.scan_duration_seconds}s</span>
            </p>
          </div>

          {result.total === 0 ? (
            <div className="bg-zinc-900/30 border border-white/10 rounded-xl p-12 text-center">
              <Scale className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
              <p className="text-zinc-400 font-medium">No bills found</p>
              <p className="text-sm text-zinc-600 mt-1">Try adding more keywords or selecting different states.</p>
            </div>
          ) : (
            <div className="bg-zinc-900/30 border border-white/10 rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="bg-zinc-950 border-b border-white/10">
                    <tr>
                      <th className="px-4 py-3">
                        <SortButton label="State" sKey="state" />
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-widest">Bill #</th>
                      <th className="px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-widest">Title</th>
                      <th className="px-4 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-widest">Category</th>
                      <th className="px-4 py-3">
                        <SortButton label="Status" sKey="status" />
                      </th>
                      <th className="px-4 py-3">
                        <SortButton label="Probability" sKey="probability" />
                      </th>
                      <th className="px-4 py-3">
                        <SortButton label="Last Action" sKey="last_action_date" />
                      </th>
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedBills.map((bill) => (
                      <BillRow key={bill.bill_id} bill={bill} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Initial empty state */}
      {!result && !loading && !error && (
        <div className="bg-zinc-900/30 border border-white/10 rounded-xl p-12 text-center">
          <Scale className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-400 font-medium">Ready to scan</p>
          <p className="text-sm text-zinc-600 mt-1">
            Select keywords and states above, then click <strong>Run Scan</strong>.
          </p>
        </div>
      )}
    </div>
  );
}
