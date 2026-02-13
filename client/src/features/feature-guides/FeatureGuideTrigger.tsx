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
          className={`text-[10px] font-mono uppercase tracking-widest transition-colors ${
            isDark
              ? 'text-zinc-500 hover:text-white'
              : 'text-zinc-400 hover:text-zinc-700'
          }`}
        >
          Show Me
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
