import { useIsLightMode } from '../hooks/useIsLightMode';
import { FeatureGuideTrigger } from '../features/feature-guides';

// ─── Theme tokens (superset of OnboardingCenter + PreTermination) ────────────

export const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl', cardLight: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl', cardDarkHover: 'hover:bg-zinc-800', cardDarkGhost: 'text-zinc-800',
  cardBorder: 'border border-stone-200 bg-stone-100 rounded-2xl', innerEl: 'bg-stone-200 rounded-xl',
  textMain: 'text-zinc-900', textMuted: 'text-stone-500', textFaint: 'text-stone-400', textDim: 'text-stone-600',
  border: 'border-stone-200', borderTab: 'border-stone-400/40', divide: 'divide-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnDisabled: 'border border-stone-300 text-stone-400 cursor-not-allowed',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  btnDanger: 'border border-red-300 text-red-700 hover:bg-red-50',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  selectCls: 'bg-white border border-stone-300 text-xs text-zinc-900 px-3 py-1.5 rounded-xl focus:outline-none focus:border-stone-400',
  rowHover: 'hover:bg-stone-50',
  alertInfo: 'border border-stone-200 bg-stone-100 rounded-xl',
  alertWarn: 'border border-amber-300 bg-amber-50 text-amber-700',
  alertError: 'border border-red-300 bg-red-50 text-red-700',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100',
  badgeDefault: 'border-stone-300 bg-stone-200 text-stone-600',
  badgeConnected: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  badgeError: 'border-red-300 bg-red-50 text-red-700',
  badgeAmber: 'border-amber-300 bg-amber-50 text-amber-700',
  statusCompleted: 'bg-emerald-50 text-emerald-700 border-emerald-300',
  statusFailed: 'bg-red-50 text-red-700 border-red-300',
  statusAmber: 'bg-amber-50 text-amber-700 border-amber-300',
  statusRunning: 'bg-blue-50 text-blue-700 border-blue-300',
  statusDefault: 'bg-stone-200 text-stone-600 border-stone-300',
  badgeGreen: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  badgeYellow: 'bg-amber-100 text-amber-800 border-amber-200',
  badgeRed: 'bg-red-100 text-red-800 border-red-200',
  badgeBlue: 'bg-blue-100 text-blue-800 border-blue-200',
  badgeGray: 'bg-stone-200 text-stone-600 border-stone-300',
  badgePurple: 'bg-violet-100 text-violet-800 border-violet-200',
  modalBg: 'bg-stone-100 rounded-2xl',
  modalHeader: 'border-b border-stone-200', modalFooter: 'border-t border-stone-200',
  comingSoon: 'opacity-75',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  labelOnDark: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  livePill: 'bg-stone-200 text-stone-600',
};

export const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl', cardLight: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-800 rounded-2xl', cardDarkHover: 'hover:bg-zinc-700', cardDarkGhost: 'text-zinc-700',
  cardBorder: 'border border-white/10 bg-zinc-900/50 rounded-2xl', innerEl: 'bg-zinc-800 rounded-xl',
  textMain: 'text-zinc-100', textMuted: 'text-zinc-500', textFaint: 'text-zinc-600', textDim: 'text-zinc-400',
  border: 'border-white/10', borderTab: 'border-white/10', divide: 'divide-white/10',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnDisabled: 'border border-white/10 text-zinc-600 cursor-not-allowed',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  btnDanger: 'border border-red-500/30 text-red-300 hover:bg-red-500/10',
  input: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-800 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',
  selectCls: 'bg-zinc-800 border border-white/10 text-xs text-zinc-100 px-3 py-1.5 rounded-xl focus:outline-none focus:border-white/20',
  rowHover: 'hover:bg-white/5',
  alertInfo: 'border border-white/10 bg-zinc-900/50 rounded-xl',
  alertWarn: 'border border-amber-500/30 bg-amber-950/30 text-amber-400',
  alertError: 'border border-red-500/30 bg-red-950/30 text-red-400',
  emptyBorder: 'border border-dashed border-white/10 bg-zinc-900/30',
  badgeDefault: 'border-zinc-700 bg-zinc-800 text-zinc-400',
  badgeConnected: 'border-emerald-500/30 bg-emerald-950/40 text-emerald-400',
  badgeError: 'border-red-500/30 bg-red-950/40 text-red-400',
  badgeAmber: 'border-amber-500/30 bg-amber-950/40 text-amber-400',
  statusCompleted: 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30',
  statusFailed: 'bg-red-950/40 text-red-400 border-red-500/30',
  statusAmber: 'bg-amber-950/40 text-amber-400 border-amber-500/30',
  statusRunning: 'bg-blue-950/40 text-blue-400 border-blue-500/30',
  statusDefault: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  badgeGreen: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  badgeYellow: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  badgeRed: 'bg-red-500/10 text-red-400 border-red-500/20',
  badgeBlue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  badgeGray: 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30',
  badgePurple: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
  modalBg: 'bg-zinc-900 border border-white/10 rounded-2xl',
  modalHeader: 'border-b border-white/10', modalFooter: 'border-t border-white/10',
  comingSoon: 'opacity-50',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  labelOnDark: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  livePill: 'bg-zinc-800 text-zinc-400',
};

export type ThemeTokens = typeof LT;

export function useTk(): ThemeTokens {
  const isLight = useIsLightMode();
  return isLight ? LT : DK;
}

// ─── PageShell ───────────────────────────────────────────────────────────────

interface PageShellProps {
  title: string;
  subtitle: string;
  guideId?: string;
  guideTourAttr?: string;
  children: React.ReactNode;
}

export function PageShell({ title, subtitle, guideId, guideTourAttr, children }: PageShellProps) {
  const t = useTk();
  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
      <div className="max-w-5xl mx-auto space-y-6 animate-in fade-in duration-500">
        <div className="flex justify-between items-start mb-12 pb-8">
          <div>
            <div className="flex items-center gap-3">
              <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>{title}</h1>
              <div className={`px-2.5 py-0.5 ${t.livePill} text-[10px] uppercase tracking-widest font-bold rounded-full`}>Live</div>
              {guideId && (
                <div data-tour={guideTourAttr}>
                  <FeatureGuideTrigger guideId={guideId} />
                </div>
              )}
            </div>
            <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>{subtitle}</p>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

// ─── TabBar ──────────────────────────────────────────────────────────────────

interface TabBarProps<T extends string> {
  tabs: { id: T; label: string }[];
  activeTab: T;
  onTabChange: (tab: T) => void;
  tourPrefix?: string;
}

export function TabBar<T extends string>({ tabs, activeTab, onTabChange, tourPrefix }: TabBarProps<T>) {
  const t = useTk();
  return (
    <div className={`border-b ${t.borderTab} -mx-4 px-4 sm:mx-0 sm:px-0`}>
      <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            data-tour={tourPrefix ? `${tourPrefix}-${tab.id}` : undefined}
            className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
              activeTab === tab.id ? t.tabActive : t.tabInactive
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
