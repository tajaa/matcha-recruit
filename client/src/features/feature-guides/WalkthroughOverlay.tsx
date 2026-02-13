import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react';
import type { WalkthroughConfig, WalkthroughStep, Placement } from './types';

interface WalkthroughOverlayProps {
  active: boolean;
  config: WalkthroughConfig;
  currentStep: WalkthroughStep | null;
  currentStepIndex: number;
  totalSteps: number;
  targetRect: DOMRect | null;
  targetFound: boolean;
  onNext: () => void;
  onBack: () => void;
  onClose: () => void;
}

const PAD = 8;

function getClipPath(rect: DOMRect): string {
  const top = rect.top - PAD;
  const left = rect.left - PAD;
  const right = rect.right + PAD;
  const bottom = rect.bottom + PAD;

  // Polygon that covers the full screen except for the rectangular cutout
  return `polygon(
    0% 0%, 0% 100%, ${left}px 100%, ${left}px ${top}px,
    ${right}px ${top}px, ${right}px ${bottom}px,
    ${left}px ${bottom}px, ${left}px 100%, 100% 100%, 100% 0%
  )`;
}

const TOOLTIP_W = 360;
const TOOLTIP_MARGIN = 12;

function clampX(x: number): number {
  return Math.max(TOOLTIP_MARGIN, Math.min(x, window.innerWidth - TOOLTIP_W - TOOLTIP_MARGIN));
}

function clampY(y: number): number {
  return Math.max(TOOLTIP_MARGIN, Math.min(y, window.innerHeight - TOOLTIP_MARGIN));
}

function getTooltipPosition(
  rect: DOMRect,
  placement: Placement
): React.CSSProperties {
  const gap = 16;

  switch (placement) {
    case 'bottom':
      return {
        top: clampY(rect.bottom + PAD + gap),
        left: clampX(rect.left + rect.width / 2 - TOOLTIP_W / 2),
      };
    case 'top':
      return {
        bottom: Math.max(TOOLTIP_MARGIN, window.innerHeight - rect.top + PAD + gap),
        left: clampX(rect.left + rect.width / 2 - TOOLTIP_W / 2),
      };
    case 'left': {
      const leftEdge = rect.left - PAD - gap - TOOLTIP_W;
      if (leftEdge < TOOLTIP_MARGIN) {
        // Not enough room on the left — flip to bottom
        return {
          top: clampY(rect.bottom + PAD + gap),
          left: clampX(rect.left + rect.width / 2 - TOOLTIP_W / 2),
        };
      }
      return {
        top: clampY(rect.top + rect.height / 2),
        left: leftEdge,
      };
    }
    case 'right': {
      const rightEdge = rect.right + PAD + gap;
      if (rightEdge + TOOLTIP_W > window.innerWidth - TOOLTIP_MARGIN) {
        // Not enough room on the right — flip to bottom
        return {
          top: clampY(rect.bottom + PAD + gap),
          left: clampX(rect.left + rect.width / 2 - TOOLTIP_W / 2),
        };
      }
      return {
        top: clampY(rect.top + rect.height / 2),
        left: rightEdge,
      };
    }
  }
}

function getArrowClass(placement: Placement, isDark: boolean): string {
  const color = isDark ? 'border-zinc-950' : 'border-white';
  const base = 'absolute w-0 h-0 border-[8px] border-transparent';

  switch (placement) {
    case 'bottom':
      return `${base} ${color.replace('border-', 'border-b-')} -top-4 left-1/2 -translate-x-1/2`;
    case 'top':
      return `${base} ${color.replace('border-', 'border-t-')} -bottom-4 left-1/2 -translate-x-1/2`;
    case 'left':
      return `${base} ${color.replace('border-', 'border-l-')} -right-4 top-1/2 -translate-y-1/2`;
    case 'right':
      return `${base} ${color.replace('border-', 'border-r-')} -left-4 top-1/2 -translate-y-1/2`;
  }
}

export function WalkthroughOverlay({
  active,
  config,
  currentStep,
  currentStepIndex,
  totalSteps,
  targetRect,
  targetFound,
  onNext,
  onBack,
  onClose,
}: WalkthroughOverlayProps) {
  const isDark = config.category === 'admin';
  const isFirst = currentStepIndex === 0;
  const isLast = currentStepIndex === totalSteps - 1;

  const overlay = (
    <AnimatePresence>
      {active && currentStep && (
        <motion.div
          key="walkthrough-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[10000]"
        >
          {/* Dark overlay with cutout */}
          <div
            className="absolute inset-0 bg-black/60"
            style={
              targetFound && targetRect
                ? { clipPath: getClipPath(targetRect) }
                : undefined
            }
            onClick={onClose}
          />

          {/* Highlight ring around target */}
          {targetFound && targetRect && (
            <div
              className="absolute pointer-events-none rounded-sm"
              style={{
                top: targetRect.top - PAD,
                left: targetRect.left - PAD,
                width: targetRect.width + PAD * 2,
                height: targetRect.height + PAD * 2,
                boxShadow: '0 0 0 2px rgba(16, 185, 129, 0.6), 0 0 20px rgba(16, 185, 129, 0.2)',
              }}
            />
          )}

          {/* Tooltip - positioned near target */}
          {targetFound && targetRect ? (
            <motion.div
              key={`step-${currentStepIndex}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.15 }}
              className={`absolute z-[10001] w-[360px] max-w-[90vw] border shadow-2xl ${
                isDark ? 'bg-zinc-950 border-white/10' : 'bg-white border-zinc-200'
              }`}
              style={getTooltipPosition(targetRect, currentStep.placement)}
            >
              <div className={getArrowClass(currentStep.placement, isDark)} />

              {/* Header */}
              <div className={`flex items-center justify-between px-4 py-3 border-b ${
                isDark ? 'border-white/10' : 'border-zinc-200'
              }`}>
                <span className={`text-xs font-bold uppercase tracking-wider ${
                  isDark ? 'text-emerald-400' : 'text-emerald-600'
                }`}>
                  {currentStep.title}
                </span>
                <span className={`text-[10px] font-mono ${
                  isDark ? 'text-zinc-500' : 'text-zinc-400'
                }`}>
                  {currentStepIndex + 1}/{totalSteps}
                </span>
              </div>

              {/* Body */}
              <div className="px-4 py-3 space-y-2">
                <p className={`text-sm leading-relaxed ${
                  isDark ? 'text-zinc-300' : 'text-zinc-700'
                }`}>
                  {currentStep.content}
                </p>

                {currentStep.action && (
                  <p className={`text-xs flex items-start gap-1.5 ${
                    isDark ? 'text-emerald-400' : 'text-emerald-600'
                  }`}>
                    <span className="mt-0.5">{'\u2192'}</span>
                    <span>{currentStep.action}</span>
                  </p>
                )}

                {currentStep.expect && (
                  <p className={`text-xs flex items-start gap-1.5 ${
                    isDark ? 'text-zinc-400' : 'text-zinc-500'
                  }`}>
                    <span className="mt-0.5">{'\u2713'}</span>
                    <span>{currentStep.expect}</span>
                  </p>
                )}
              </div>

              {/* Footer */}
              <div className={`flex items-center justify-between px-4 py-3 border-t ${
                isDark ? 'border-white/10' : 'border-zinc-200'
              }`}>
                <div>
                  {isFirst ? (
                    <button
                      onClick={onClose}
                      className={`text-[10px] font-mono uppercase tracking-widest transition-colors ${
                        isDark ? 'text-zinc-500 hover:text-zinc-300' : 'text-zinc-400 hover:text-zinc-600'
                      }`}
                    >
                      Close
                    </button>
                  ) : (
                    <button
                      onClick={onBack}
                      className={`flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest transition-colors ${
                        isDark ? 'text-zinc-400 hover:text-white' : 'text-zinc-500 hover:text-zinc-700'
                      }`}
                    >
                      <ChevronLeft className="w-3 h-3" />
                      Back
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onNext}
                    className={`flex items-center gap-1.5 px-4 py-1.5 text-[10px] font-mono font-bold uppercase tracking-widest transition-colors ${
                      isDark
                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                        : 'bg-zinc-900 hover:bg-zinc-800 text-white'
                    }`}
                  >
                    {isLast ? 'Done' : 'Next'}
                    {!isLast && <ChevronRight className="w-3 h-3" />}
                  </button>
                  <button
                    onClick={onClose}
                    className={`p-1 transition-colors ${
                      isDark ? 'text-zinc-500 hover:text-white' : 'text-zinc-400 hover:text-zinc-700'
                    }`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </motion.div>
          ) : (
            /* Target NOT found — centered warning */
            <motion.div
              key="not-found"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[10001] w-[400px] max-w-[90vw] border shadow-2xl ${
                isDark ? 'bg-zinc-950 border-white/10' : 'bg-white border-zinc-200'
              }`}
            >
              {/* Header */}
              <div className={`flex items-center justify-between px-4 py-3 border-b ${
                isDark ? 'border-white/10' : 'border-zinc-200'
              }`}>
                <span className={`text-xs font-bold uppercase tracking-wider ${
                  isDark ? 'text-emerald-400' : 'text-emerald-600'
                }`}>
                  {currentStep.title}
                </span>
                <span className={`text-[10px] font-mono ${
                  isDark ? 'text-zinc-500' : 'text-zinc-400'
                }`}>
                  {currentStepIndex + 1}/{totalSteps}
                </span>
              </div>

              {/* Body */}
              <div className="px-4 py-4 space-y-3">
                <p className={`text-sm leading-relaxed ${
                  isDark ? 'text-zinc-300' : 'text-zinc-700'
                }`}>
                  {currentStep.content}
                </p>

                {currentStep.ifMissing && (
                  <div className={`flex items-start gap-2 px-3 py-2 rounded text-xs ${
                    isDark
                      ? 'bg-amber-500/10 border border-amber-500/20 text-amber-400'
                      : 'bg-amber-50 border border-amber-200 text-amber-700'
                  }`}>
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    <span>{currentStep.ifMissing}</span>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className={`flex items-center justify-between px-4 py-3 border-t ${
                isDark ? 'border-white/10' : 'border-zinc-200'
              }`}>
                <div>
                  {isFirst ? (
                    <button
                      onClick={onClose}
                      className={`text-[10px] font-mono uppercase tracking-widest transition-colors ${
                        isDark ? 'text-zinc-500 hover:text-zinc-300' : 'text-zinc-400 hover:text-zinc-600'
                      }`}
                    >
                      Close
                    </button>
                  ) : (
                    <button
                      onClick={onBack}
                      className={`flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest transition-colors ${
                        isDark ? 'text-zinc-400 hover:text-white' : 'text-zinc-500 hover:text-zinc-700'
                      }`}
                    >
                      <ChevronLeft className="w-3 h-3" />
                      Back
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onNext}
                    className={`flex items-center gap-1.5 px-4 py-1.5 text-[10px] font-mono font-bold uppercase tracking-widest transition-colors ${
                      isDark
                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                        : 'bg-zinc-900 hover:bg-zinc-800 text-white'
                    }`}
                  >
                    {isLast ? 'Done' : 'Next'}
                    {!isLast && <ChevronRight className="w-3 h-3" />}
                  </button>
                  <button
                    onClick={onClose}
                    className={`p-1 transition-colors ${
                      isDark ? 'text-zinc-500 hover:text-white' : 'text-zinc-400 hover:text-zinc-700'
                    }`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );

  return createPortal(overlay, document.body);
}
