import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { upcomingDeadlines } from '../api/client';
import type { UpcomingItem } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import {
  AlertCircle,
  Shield,
  Award,
  GraduationCap,
  HeartPulse,
  FileText,
  AlertTriangle,
  Scale,
  Fingerprint,
  FileSignature,
  ClipboardList,
  ChevronRight,
  Clock,
} from 'lucide-react';

// ─── Category metadata ───────────────────────────────────────────────────────

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  compliance:  <Shield size={14} />,
  credential:  <Award size={14} />,
  training:    <GraduationCap size={14} />,
  cobra:       <HeartPulse size={14} />,
  policy:      <FileText size={14} />,
  ir:          <AlertTriangle size={14} />,
  er:          <Scale size={14} />,
  i9:          <Fingerprint size={14} />,
  separation:  <FileSignature size={14} />,
  onboarding:  <ClipboardList size={14} />,
};

const CATEGORY_LABEL: Record<string, string> = {
  compliance:  'Compliance',
  credential:  'Credential',
  training:    'Training',
  cobra:       'COBRA',
  policy:      'Policy',
  ir:          'Incident',
  er:          'ER Case',
  i9:          'I-9',
  separation:  'Separation',
  onboarding:  'Onboarding',
};

const ALL_CATEGORIES = Object.keys(CATEGORY_LABEL);

// ─── Theme tokens ────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  rowHover: 'hover:bg-stone-50',
  rowOverdue: 'bg-red-50/60',
  divide: 'divide-stone-200',
  filterActive: 'bg-zinc-900 text-zinc-50',
  filterIdle: 'bg-stone-200 text-stone-500 hover:text-zinc-900',
  dotCritical: 'bg-red-500',
  dotWarning: 'bg-amber-500',
  dotInfo: 'bg-stone-400',
  badge: 'bg-stone-200 text-stone-600',
  icon: 'text-stone-400',
  arrow: 'text-stone-400 group-hover:text-zinc-900',
  emptyBg: 'bg-stone-100',
  emptyIcon: 'text-stone-300',
  emptyText: 'text-stone-400',
  skeleton: 'bg-stone-200',
  countBadge: 'bg-stone-200 text-stone-600',
};

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  rowHover: 'hover:bg-white/5',
  rowOverdue: 'bg-red-950/30',
  divide: 'divide-white/10',
  filterActive: 'bg-zinc-100 text-zinc-900',
  filterIdle: 'bg-zinc-800 text-zinc-400 hover:text-zinc-100',
  dotCritical: 'bg-red-500',
  dotWarning: 'bg-amber-500',
  dotInfo: 'bg-zinc-600',
  badge: 'bg-zinc-800 text-zinc-400',
  icon: 'text-zinc-600',
  arrow: 'text-zinc-600 group-hover:text-zinc-100',
  emptyBg: 'bg-zinc-900',
  emptyIcon: 'text-zinc-700',
  emptyText: 'text-zinc-600',
  skeleton: 'bg-zinc-800',
  countBadge: 'bg-zinc-800 text-zinc-400',
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relativeDate(daysUntil: number): string {
  if (daysUntil === 0) return 'Today';
  if (daysUntil === 1) return 'Tomorrow';
  if (daysUntil === -1) return '1 day overdue';
  if (daysUntil < 0) return `${Math.abs(daysUntil)} days overdue`;
  return `in ${daysUntil} days`;
}

const DAYS_OPTIONS = [30, 60, 90] as const;

// ─── Component ───────────────────────────────────────────────────────────────

export default function UpcomingDeadlines() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const navigate = useNavigate();

  const [items, setItems] = useState<UpcomingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [days, setDays] = useState<number>(90);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    upcomingDeadlines.get(days).then((res) => {
      if (!cancelled) {
        setItems(res.items);
        setLoading(false);
      }
    }).catch((err) => {
      if (!cancelled) {
        setError(err?.message || 'Failed to load');
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [days]);

  const filtered = items.filter((item) => {
    if (categoryFilter !== 'all' && item.category !== categoryFilter) return false;
    if (severityFilter !== 'all' && item.severity !== severityFilter) return false;
    return true;
  });

  // Categories present in data (for filter dropdown)
  const presentCategories = [...new Set(items.map((i) => i.category))];

  return (
    <div className="max-w-4xl mx-auto py-4 px-4 sm:px-6 space-y-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <Clock className={`w-5 h-5 ${t.textMuted}`} />
          <h1 className={`text-lg font-semibold ${t.textMain}`}>Upcoming Deadlines</h1>
          <span className={`text-xs px-2 py-0.5 rounded-full ${t.countBadge}`}>
            {filtered.length}
          </span>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Days selector */}
          {DAYS_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`text-xs px-3 py-1.5 rounded-full font-medium transition-colors ${
                days === d ? t.filterActive : t.filterIdle
              }`}
            >
              {d}d
            </button>
          ))}

          <span className={`mx-1 ${t.textFaint}`}>|</span>

          {/* Category filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className={`text-xs px-2 py-1.5 rounded-lg border-0 font-medium cursor-pointer ${t.filterIdle} appearance-none`}
          >
            <option value="all">All categories</option>
            {presentCategories.map((cat) => (
              <option key={cat} value={cat}>{CATEGORY_LABEL[cat] || cat}</option>
            ))}
          </select>

          {/* Severity filter */}
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className={`text-xs px-2 py-1.5 rounded-lg border-0 font-medium cursor-pointer ${t.filterIdle} appearance-none`}
          >
            <option value="all">All severity</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </div>

        {/* List */}
        <div className={`${t.card} overflow-hidden`}>
          {loading ? (
            <div className="p-4 space-y-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className={`h-12 ${t.skeleton} rounded-lg animate-pulse`} />
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center">
              <AlertCircle className={`w-8 h-8 mx-auto mb-2 ${t.emptyIcon}`} />
              <p className={`text-sm ${t.emptyText}`}>{error}</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center">
              <Clock className={`w-8 h-8 mx-auto mb-2 ${t.emptyIcon}`} />
              <p className={`text-sm ${t.emptyText}`}>
                {items.length === 0 ? 'No upcoming deadlines' : 'No items match filters'}
              </p>
            </div>
          ) : (
            <div className={`divide-y ${t.divide}`}>
              {filtered.map((item, idx) => (
                <button
                  key={`${item.category}-${item.date}-${idx}`}
                  onClick={() => navigate(item.link)}
                  className={`group w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${t.rowHover} ${
                    item.days_until < 0 ? t.rowOverdue : ''
                  }`}
                >
                  {/* Severity dot */}
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    item.severity === 'critical' ? t.dotCritical
                    : item.severity === 'warning' ? t.dotWarning
                    : t.dotInfo
                  }`} />

                  {/* Category icon + badge */}
                  <span className={`flex-shrink-0 ${t.icon}`}>
                    {CATEGORY_ICON[item.category] || <AlertCircle size={14} />}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0 ${t.badge}`}>
                    {CATEGORY_LABEL[item.category] || item.category}
                  </span>

                  {/* Title + subtitle */}
                  <div className="flex-1 min-w-0">
                    <span className={`text-sm font-medium truncate block ${t.textMain}`}>
                      {item.title}
                    </span>
                    {item.subtitle && (
                      <span className={`text-xs truncate block ${t.textMuted}`}>
                        {item.subtitle}
                      </span>
                    )}
                  </div>

                  {/* Relative date */}
                  <span className={`text-xs whitespace-nowrap flex-shrink-0 font-medium ${
                    item.days_until < 0 ? 'text-red-500'
                    : item.days_until <= 14 ? 'text-amber-500'
                    : t.textFaint
                  }`}>
                    {relativeDate(item.days_until)}
                  </span>

                  <ChevronRight className={`w-3.5 h-3.5 flex-shrink-0 ${t.arrow}`} />
                </button>
              ))}
            </div>
          )}
        </div>
    </div>
  );
}

