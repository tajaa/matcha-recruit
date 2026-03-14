import { useState, useEffect, useMemo } from 'react';
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
  Landmark,
  BookMarked,
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
  legislation: <Landmark size={14} />,
  requirement: <BookMarked size={14} />,
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
  legislation: 'Legislation',
  requirement: 'Requirement',
};

// ─── Urgency bands ───────────────────────────────────────────────────────────

type Band = 'overdue' | 'this_week' | 'this_month' | 'later';

const BANDS: { key: Band; label: string; test: (d: number) => boolean }[] = [
  { key: 'overdue',    label: 'Overdue',    test: (d) => d < 0 },
  { key: 'this_week',  label: 'This Week',  test: (d) => d >= 0 && d <= 7 },
  { key: 'this_month', label: 'This Month', test: (d) => d > 7 && d <= 30 },
  { key: 'later',      label: 'Later',      test: (d) => d > 30 },
];

// ─── Theme tokens ────────────────────────────────────────────────────────────

const LT = {
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
  emptyIcon: 'text-stone-300',
  emptyText: 'text-stone-400',
  skeleton: 'bg-stone-200',
  countBadge: 'bg-stone-200 text-stone-600',
  sectionBg: 'bg-stone-200/60',
  sectionText: 'text-stone-500',
  sectionCount: 'bg-stone-300 text-stone-600',
  overdueSection: 'text-red-700',
  overdueSectionCount: 'bg-red-100 text-red-700',
};

const DK = {
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
  emptyIcon: 'text-zinc-700',
  emptyText: 'text-zinc-600',
  skeleton: 'bg-zinc-800',
  countBadge: 'bg-zinc-800 text-zinc-400',
  sectionBg: 'bg-white/5',
  sectionText: 'text-zinc-500',
  sectionCount: 'bg-zinc-800 text-zinc-400',
  overdueSection: 'text-red-400',
  overdueSectionCount: 'bg-red-950 text-red-400',
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relativeDate(daysUntil: number): string {
  if (daysUntil === 0) return 'Today';
  if (daysUntil === 1) return 'Tomorrow';
  if (daysUntil === -1) return '1 day overdue';
  if (daysUntil < 0) return `${Math.abs(daysUntil)}d overdue`;
  return `in ${daysUntil}d`;
}

const DAYS_OPTIONS = [30, 60, 90] as const;

// ─── Row component ───────────────────────────────────────────────────────────

function ItemRow({ item, t, onClick }: { item: UpcomingItem; t: typeof LT; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`group w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${t.rowHover} ${
        item.days_until < 0 ? t.rowOverdue : ''
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        item.severity === 'critical' ? t.dotCritical
        : item.severity === 'warning' ? t.dotWarning
        : t.dotInfo
      }`} />

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

      <span className={`text-xs whitespace-nowrap flex-shrink-0 font-medium ${
        item.days_until < 0 ? 'text-red-500'
        : item.days_until <= 14 ? 'text-amber-500'
        : t.textFaint
      }`}>
        {relativeDate(item.days_until)}
      </span>

      <ChevronRight className={`w-3.5 h-3.5 flex-shrink-0 ${t.arrow}`} />
    </button>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function UpcomingDeadlines() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const navigate = useNavigate();

  const [items, setItems] = useState<UpcomingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const filtered = useMemo(() =>
    items.filter((item) => {
      if (categoryFilter !== 'all' && item.category !== categoryFilter) return false;
      if (severityFilter !== 'all' && item.severity !== severityFilter) return false;
      return true;
    }),
    [items, categoryFilter, severityFilter],
  );

  // Band → category → items
  const grouped = useMemo(() => {
    const map = new Map<Band, Map<string, UpcomingItem[]>>();
    for (const band of BANDS) map.set(band.key, new Map());
    for (const item of filtered) {
      const band = BANDS.find((b) => b.test(item.days_until)) || BANDS[3];
      const catMap = map.get(band.key)!;
      if (!catMap.has(item.category)) catMap.set(item.category, []);
      catMap.get(item.category)!.push(item);
    }
    // Sort categories: credentials/i9 first, then rest alphabetically
    const PRIORITY_CATS = ['credential', 'i9'];
    for (const [bandKey, catMap] of map) {
      const sorted = new Map<string, UpcomingItem[]>(
        [...catMap.entries()].sort(([a], [b]) => {
          const ai = PRIORITY_CATS.indexOf(a);
          const bi = PRIORITY_CATS.indexOf(b);
          if (ai !== -1 && bi !== -1) return ai - bi;
          if (ai !== -1) return -1;
          if (bi !== -1) return 1;
          return (CATEGORY_LABEL[a] || a).localeCompare(CATEGORY_LABEL[b] || b);
        })
      );
      map.set(bandKey, sorted);
    }
    return map;
  }, [filtered]);

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

      {/* Grouped list */}
      {loading ? (
        <div className={`${t.card} p-4 space-y-3`}>
          {[...Array(6)].map((_, i) => (
            <div key={i} className={`h-12 ${t.skeleton} rounded-lg animate-pulse`} />
          ))}
        </div>
      ) : error ? (
        <div className={`${t.card} p-8 text-center`}>
          <AlertCircle className={`w-8 h-8 mx-auto mb-2 ${t.emptyIcon}`} />
          <p className={`text-sm ${t.emptyText}`}>{error}</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className={`${t.card} p-8 text-center`}>
          <Clock className={`w-8 h-8 mx-auto mb-2 ${t.emptyIcon}`} />
          <p className={`text-sm ${t.emptyText}`}>
            {items.length === 0 ? 'No upcoming deadlines' : 'No items match filters'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {BANDS.map(({ key, label }) => {
            const catMap = grouped.get(key)!;
            if (catMap.size === 0) return null;
            const isOverdue = key === 'overdue';
            const bandTotal = [...catMap.values()].reduce((s, arr) => s + arr.length, 0);

            return (
              <div key={key} className="space-y-2">
                {/* Band header */}
                <div className="flex items-center gap-2 px-1">
                  <span className={`text-xs font-semibold uppercase tracking-wider ${
                    isOverdue ? t.overdueSection : t.sectionText
                  }`}>
                    {label}
                  </span>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                    isOverdue ? t.overdueSectionCount : t.sectionCount
                  }`}>
                    {bandTotal}
                  </span>
                </div>

                {/* Category sub-groups */}
                {[...catMap.entries()].map(([cat, catItems]) => (
                  <div key={cat} className={`${t.card} overflow-hidden`}>
                    <div className={`flex items-center gap-2 px-4 py-1.5 ${t.sectionBg}`}>
                      <span className={`flex-shrink-0 ${t.icon}`}>
                        {CATEGORY_ICON[cat] || <AlertCircle size={13} />}
                      </span>
                      <span className={`text-[11px] font-semibold ${t.sectionText}`}>
                        {CATEGORY_LABEL[cat] || cat}
                      </span>
                      <span className={`text-[10px] font-medium ${t.textFaint}`}>
                        {catItems.length}
                      </span>
                    </div>
                    <div className={`divide-y ${t.divide}`}>
                      {catItems.map((item, idx) => (
                        <ItemRow
                          key={`${item.date}-${idx}`}
                          item={item}
                          t={t}
                          onClick={() => navigate(item.link)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
