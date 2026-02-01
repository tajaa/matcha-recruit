import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, ChevronRight, ChevronLeft, Shield, MapPin, FileCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface WizardStep {
  icon: React.ElementType;
  heading: string;
  body: string;
}

interface WizardConfig {
  title: string;
  steps: WizardStep[];
  ctaLabel: string;
  ctaPath: string;
}

const WIZARD_CONFIGS: Record<string, WizardConfig> = {
  compliance: {
    title: 'Compliance Setup',
    steps: [
      {
        icon: Shield,
        heading: 'Stay Compliant Across Every Location',
        body: 'The compliance module monitors labor laws, posting requirements, and regulatory changes for each jurisdiction where you operate. Get alerts before deadlines and keep your business protected.',
      },
      {
        icon: MapPin,
        heading: 'Add Your Business Locations',
        body: 'To get started, you\'ll add the cities and states where your company has employees or offices. We\'ll automatically match each location to its applicable federal, state, and local regulations.',
      },
      {
        icon: FileCheck,
        heading: 'You\'re One Step Away',
        body: 'Once your locations are set up, we\'ll research the compliance requirements for each jurisdiction and keep you updated as laws change. Let\'s add your first location now.',
      },
    ],
    ctaLabel: 'Set Up Locations',
    ctaPath: '/app/matcha/compliance',
  },
};

const DISMISS_KEY_PREFIX = 'onboarding_dismissed_';

export function OnboardingWizard() {
  const { onboardingNeeded } = useAuth();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [dismissed, setDismissed] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const key of Object.keys(WIZARD_CONFIGS)) {
      if (sessionStorage.getItem(`${DISMISS_KEY_PREFIX}${key}`)) {
        initial[key] = true;
      }
    }
    return initial;
  });

  const dismiss = useCallback((feature: string) => {
    sessionStorage.setItem(`${DISMISS_KEY_PREFIX}${feature}`, '1');
    setDismissed(prev => ({ ...prev, [feature]: true }));
  }, []);

  // Find first feature that needs onboarding and hasn't been dismissed
  const activeFeature = Object.keys(onboardingNeeded).find(
    key => onboardingNeeded[key] && WIZARD_CONFIGS[key] && !dismissed[key]
  );

  if (!activeFeature) return null;

  const config = WIZARD_CONFIGS[activeFeature];
  const step = config.steps[currentStep];
  const isLastStep = currentStep === config.steps.length - 1;
  const StepIcon = step.icon;

  const handleNext = () => {
    if (isLastStep) {
      dismiss(activeFeature);
      navigate(config.ctaPath);
    } else {
      setCurrentStep(prev => prev + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
    }
  };

  const handleDismiss = () => {
    dismiss(activeFeature);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="relative w-full max-w-lg mx-4 border border-white/10 bg-zinc-950 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="text-[10px] uppercase tracking-[0.2em] text-emerald-400 font-mono font-bold">
            {config.title}
          </div>
          <button
            onClick={handleDismiss}
            className="p-1 text-zinc-500 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Progress */}
        <div className="flex gap-1 px-6 pt-6">
          {config.steps.map((_, i) => (
            <div
              key={i}
              className={`h-0.5 flex-1 rounded-full transition-colors duration-300 ${
                i <= currentStep ? 'bg-emerald-500' : 'bg-zinc-800'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="p-6 pt-8 pb-4">
          <div className="flex items-center justify-center mb-8">
            <div className="p-4 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <StepIcon className="w-8 h-8 text-emerald-400" />
            </div>
          </div>
          <h2 className="text-xl font-bold text-white text-center mb-4 tracking-tight">
            {step.heading}
          </h2>
          <p className="text-sm text-zinc-400 text-center leading-relaxed max-w-sm mx-auto">
            {step.body}
          </p>
        </div>

        {/* Step indicator */}
        <div className="text-center pb-4">
          <span className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest">
            Step {currentStep + 1} of {config.steps.length}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between p-6 border-t border-white/10">
          <div>
            {currentStep > 0 ? (
              <button
                onClick={handleBack}
                className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
              >
                <ChevronLeft className="w-3 h-3" />
                Back
              </button>
            ) : (
              <button
                onClick={handleDismiss}
                className="text-xs font-mono uppercase tracking-widest text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                Skip for now
              </button>
            )}
          </div>
          <button
            onClick={handleNext}
            className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono uppercase tracking-widest transition-colors font-bold"
          >
            {isLastStep ? config.ctaLabel : 'Next'}
            <ChevronRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default OnboardingWizard;
