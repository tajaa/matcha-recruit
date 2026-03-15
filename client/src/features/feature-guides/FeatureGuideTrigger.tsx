import { useWalkthrough } from './useWalkthrough';
import { WalkthroughOverlay } from './WalkthroughOverlay';
import type { GuideKey } from './types';

interface FeatureGuideTriggerProps {
  guideId: GuideKey;
  className?: string;
}

export function FeatureGuideTrigger({ guideId, className = '' }: FeatureGuideTriggerProps) {
  const {
    isNew, active, currentStep, currentStepIndex, totalSteps,
    config, targetRect, targetFound, start, stop, next, back,
  } = useWalkthrough(guideId);

  return (
    <>
      <div className={`flex items-center gap-2 ${className}`}>
        {isNew && (
          <button onClick={start} className="px-2 py-0.5 text-[9px] font-mono font-bold uppercase tracking-widest bg-stone-200 text-stone-600 border border-stone-300 hover:bg-stone-300">
            New
          </button>
        )}
        <button
          onClick={start}
          className={`inline-flex items-center gap-2 rounded border px-2.5 py-1 text-[10px] font-mono uppercase tracking-widest ${
            active
              ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
              : 'border-stone-300 bg-stone-200 text-stone-600 hover:bg-stone-300'
          }`}
          title="Start interactive walkthrough"
          aria-label="Start interactive walkthrough"
        >
          <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-zinc-50 animate-pulse' : 'bg-stone-400'}`} />
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
