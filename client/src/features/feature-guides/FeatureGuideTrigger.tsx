import { useWalkthrough } from './useWalkthrough';
import { WalkthroughOverlay } from './WalkthroughOverlay';
import type { GuideKey } from './types';

interface FeatureGuideTriggerProps {
  guideId: GuideKey;
  className?: string;
  variant?: 'dark' | 'light';
}

export function FeatureGuideTrigger({ guideId, className = '', variant = 'dark' }: FeatureGuideTriggerProps) {
  const {
    isNew, active, currentStep, currentStepIndex, totalSteps,
    config, targetRect, targetFound, start, stop, next, back,
  } = useWalkthrough(guideId);

  const isDark = variant === 'dark';

  return (
    <>
      <div className={`flex items-center gap-2 ${className}`}>
        {isNew && (
          <button
            onClick={start}
            className={`px-2 py-0.5 text-[9px] font-mono font-bold uppercase tracking-widest transition-colors ${
              isDark
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20'
                : 'bg-emerald-50 text-emerald-600 border border-emerald-200 hover:bg-emerald-100'
            } animate-pulse`}
          >
            New
          </button>
        )}
        <button
          onClick={start}
          className={`inline-flex items-center gap-2 rounded border px-2.5 py-1 text-[10px] font-mono uppercase tracking-widest transition-colors ${
            isDark
              ? active
                ? 'border-emerald-400/50 bg-emerald-500/25 text-emerald-100 shadow-[0_0_18px_rgba(16,185,129,0.25)]'
                : 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25 hover:text-white'
              : active
                ? 'border-emerald-500/60 bg-emerald-100 text-emerald-700'
                : 'border-emerald-500/50 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
          }`}
          title="Start interactive walkthrough"
          aria-label="Start interactive walkthrough"
        >
          <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-emerald-200 animate-pulse' : 'bg-emerald-400'}`} />
          <span>Show Me</span>
        </button>
      </div>

      <WalkthroughOverlay
        active={active}
        config={config}
        currentStep={currentStep}
        currentStepIndex={currentStepIndex}
        totalSteps={totalSteps}
        targetRect={targetRect}
        targetFound={targetFound}
        onNext={next}
        onBack={back}
        onClose={stop}
      />
    </>
  );
}
