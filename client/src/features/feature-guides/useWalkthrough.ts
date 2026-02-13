import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { WALKTHROUGH_CONFIGS } from './walkthroughs';
import { hasSeenGuide, markGuideSeen } from './storage';
import type { WalkthroughConfig, WalkthroughStep, GuideKey } from './types';

interface UseWalkthroughReturn {
  isNew: boolean;
  active: boolean;
  currentStepIndex: number;
  currentStep: WalkthroughStep | null;
  totalSteps: number;
  config: WalkthroughConfig;
  targetRect: DOMRect | null;
  targetFound: boolean;
  start: () => void;
  stop: () => void;
  next: () => void;
  back: () => void;
}

export function useWalkthrough(guideId: GuideKey): UseWalkthroughReturn {
  const { user } = useAuth();
  const userId = user?.id ?? '';
  const config = WALKTHROUGH_CONFIGS[guideId];

  const [isNew, setIsNew] = useState(() => {
    if (!userId) return false;
    return !hasSeenGuide(guideId, userId);
  });
  const [active, setActive] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [targetFound, setTargetFound] = useState(false);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    if (userId) {
      setIsNew(!hasSeenGuide(guideId, userId));
    }
  }, [guideId, userId]);

  const computeRect = useCallback(() => {
    if (!active || !config) return;
    const step = config.steps[currentStepIndex];
    if (!step) return;

    const el = document.querySelector(`[data-tour="${step.target}"]`);
    if (el) {
      setTargetFound(true);
      setTargetRect(el.getBoundingClientRect());
    } else {
      setTargetFound(false);
      setTargetRect(null);
    }
  }, [active, config, currentStepIndex]);

  // Scroll to target and compute rect when step changes
  useEffect(() => {
    if (!active || !config) return;
    const step = config.steps[currentStepIndex];
    if (!step) return;

    const el = document.querySelector(`[data-tour="${step.target}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Wait for scroll to settle, then compute rect
      scrollTimeoutRef.current = setTimeout(() => {
        computeRect();
      }, 300);
    } else {
      setTargetFound(false);
      setTargetRect(null);
    }

    return () => {
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    };
  }, [active, config, currentStepIndex, computeRect]);

  // Recompute on resize/scroll (debounced)
  useEffect(() => {
    if (!active) return;

    let debounceTimer: ReturnType<typeof setTimeout>;
    const handleUpdate = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(computeRect, 100);
    };

    window.addEventListener('resize', handleUpdate);
    window.addEventListener('scroll', handleUpdate, true);

    return () => {
      clearTimeout(debounceTimer);
      window.removeEventListener('resize', handleUpdate);
      window.removeEventListener('scroll', handleUpdate, true);
    };
  }, [active, computeRect]);

  // Keyboard navigation
  useEffect(() => {
    if (!active) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setActive(false);
      } else if (e.key === 'ArrowRight') {
        setCurrentStepIndex((i) => Math.min(i + 1, config.steps.length - 1));
      } else if (e.key === 'ArrowLeft') {
        setCurrentStepIndex((i) => Math.max(i - 1, 0));
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [active, config]);

  // Lock body scroll when active
  useEffect(() => {
    if (active) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [active]);

  const start = useCallback(() => {
    setCurrentStepIndex(0);
    setActive(true);
    if (userId) {
      markGuideSeen(guideId, userId);
      setIsNew(false);
    }
  }, [guideId, userId]);

  const stop = useCallback(() => {
    setActive(false);
  }, []);

  const next = useCallback(() => {
    if (currentStepIndex >= config.steps.length - 1) {
      setActive(false);
    } else {
      setCurrentStepIndex((i) => i + 1);
    }
  }, [currentStepIndex, config]);

  const back = useCallback(() => {
    setCurrentStepIndex((i) => Math.max(i - 1, 0));
  }, []);

  return {
    isNew,
    active,
    currentStepIndex,
    currentStep: active && config ? config.steps[currentStepIndex] ?? null : null,
    totalSteps: config.steps.length,
    config,
    targetRect,
    targetFound,
    start,
    stop,
    next,
    back,
  };
}
