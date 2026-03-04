import { useEffect, useRef, useState } from 'react';

const SIMULATED_STEPS: Record<string, string[]> = {
  timeline: [
    'Extracting dates and events from documents...',
    'Cross-referencing witness accounts...',
    'Ordering chronological sequence...',
    'Identifying gaps in timeline...',
    'Compiling final timeline...',
  ],
  discrepancies: [
    'Parsing document statements...',
    'Comparing accounts across sources...',
    'Flagging inconsistencies...',
    'Assessing severity levels...',
    'Generating discrepancy report...',
  ],
  policy: [
    'Loading company policy documents...',
    'Scanning evidence against policies...',
    'Evaluating compliance requirements...',
    'Identifying potential violations...',
    'Compiling policy review...',
  ],
  review: [
    'Reviewing uploaded evidence...',
    'Reconstructing event timeline...',
    'Analyzing witness statements...',
    'Checking against company policies...',
    'Generating guidance...',
  ],
};

interface AnalysisConsoleProps {
  title: string;
  analysisType: string;
  /** Real-time step from WebSocket or handler */
  currentStep?: string;
  detail?: string;
  active: boolean;
}

export function AnalysisConsole({ title, analysisType, currentStep, detail, active }: AnalysisConsoleProps) {
  const [steps, setSteps] = useState<string[]>([]);
  const stepIndexRef = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastRealStepRef = useRef<string | null>(null);

  // Reset on activation
  useEffect(() => {
    if (active) {
      setSteps([]);
      stepIndexRef.current = 0;
      lastRealStepRef.current = null;
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [active]);

  // Simulated step advancement
  useEffect(() => {
    if (!active) return;
    const simSteps = SIMULATED_STEPS[analysisType] || SIMULATED_STEPS.review;

    intervalRef.current = setInterval(() => {
      if (stepIndexRef.current < simSteps.length) {
        const step = simSteps[stepIndexRef.current];
        setSteps(prev => {
          if (prev.includes(step)) return prev;
          return [...prev, step];
        });
        stepIndexRef.current++;
      }
    }, 3500);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [active, analysisType]);

  // Inject real WebSocket steps
  useEffect(() => {
    if (!active || !currentStep || currentStep === lastRealStepRef.current) return;
    lastRealStepRef.current = currentStep;
    setSteps(prev => {
      if (prev.includes(currentStep)) return prev;
      return [...prev, currentStep];
    });
  }, [active, currentStep]);

  if (!active) return null;

  const progressPct = Math.min(95, Math.max(8, (steps.length / 6) * 100));

  return (
    <div className="relative border border-emerald-500/25 rounded-sm overflow-hidden animate-border-breathe">
      <div className="bg-zinc-900/95 bg-noise p-4 space-y-3">
        {/* Scanline overlay */}
        <div className="analysis-console-scanline absolute inset-0" />

        {/* Header */}
        <div className="relative flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.2em] font-mono font-medium text-emerald-400/80">
            {title}
          </span>
          <span className="inline-block w-1.5 h-3 bg-emerald-400 animate-cursor-blink" />
        </div>

        {/* Step log */}
        <div className="relative space-y-1.5 font-mono">
          {steps.map((step, i) => {
            const isCurrent = i === steps.length - 1;
            return (
              <div
                key={i}
                className="animate-fade-in-up"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                {isCurrent ? (
                  <div className="flex items-start gap-2 relative">
                    <span className="mt-1 block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot flex-shrink-0" />
                    <span className="text-xs text-emerald-300 animate-text-flicker relative">
                      {step}
                      <span className="absolute inset-0 animate-shimmer-sweep rounded" />
                    </span>
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-500/60 text-xs flex-shrink-0">✓</span>
                    <span className="text-xs text-emerald-400/50">{step}</span>
                  </div>
                )}
              </div>
            );
          })}
          {steps.length === 0 && (
            <div className="flex items-start gap-2">
              <span className="mt-1 block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot flex-shrink-0" />
              <span className="text-xs text-emerald-300 animate-text-flicker">Initializing analysis...</span>
            </div>
          )}
        </div>

        {/* Detail sub-line */}
        {detail && (
          <div className="relative text-[10px] text-emerald-400/40 font-mono pl-3.5">
            {detail}
          </div>
        )}

        {/* Progress bar */}
        <div className="relative h-0.5 bg-zinc-800 rounded-full overflow-hidden mt-2">
          <div
            className="h-full bg-emerald-500/70 rounded-full transition-all duration-700 ease-out animate-progress-glow"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>
    </div>
  );
}
