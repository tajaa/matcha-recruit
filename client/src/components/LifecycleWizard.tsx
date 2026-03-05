import React, { useState } from 'react';
import { CheckCircle, ChevronDown } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useIsLightMode } from '../hooks/useIsLightMode';

export type LifecycleStepIcon =
  | 'locations' | 'research' | 'alerts' | 'posters' | 'audit'
  | 'onboard' | 'provision' | 'invite' | 'track' | 'directory'
  | 'draft' | 'generate' | 'send'
  | 'intake' | 'evidence' | 'guidance' | 'analysis' | 'decision' | 'resolution' | 'closeout'
  | 'editor' | 'review' | 'activate' | 'publish' | 'acknowledge'
  | 'setup' | 'employee' | 'accepted' | 'in_progress' | 'complete' | 'ready' | 'documents' | 'training'
  | 'policy' | 'request' | 'calendar' | 'balance' | 'allocate' | 'approve'
  | 'report' | 'investigate' | 'action' | 'resolve' | 'analyze'
  | 'collect' | 'categorize' | 'score'
  | 'template' | 'launch' | 'self' | 'manager' | 'finalize'
  | 'config' | 'broadcast' | 'capture' | 'trends';

export interface LifecycleStep {
  id: number;
  icon: LifecycleStepIcon;
  title: string;
  description: string;
  action?: string;
}

interface LifecycleWizardProps {
  steps: LifecycleStep[];
  activeStep: number;
  storageKey: string;
  title?: string;
}

const STEP_ICONS: Record<LifecycleStepIcon, (props: { className: string }) => React.ReactElement> = {
  // Compliance
  'locations': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 17C10 17 4 11 4 7C4 3.68629 6.68629 1 10 1C13.3137 1 16 3.68629 16 7C16 11 10 17 10 17Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="10" cy="7" r="2" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  ),
  'research': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  ),
  'alerts': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 3V17M3 10H17M14.5 5.5L5.5 14.5M14.5 14.5L5.5 5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'posters': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="5" y="4" width="10" height="12" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 7H13M7 10H13M7 13H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'audit': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 10L8 14L16 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // Employees
  'onboard': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 5V15M5 10H15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  ),
  'provision': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="5" y="5" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 8V12M8 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M5 10H3.5M16.5 10H15M10 5V3.5M10 16.5V15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'invite': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M16 5L4 10L10 11L11 17L16 5Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'track': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 16V12M10 16V8M16 16V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M3 17H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'directory': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="8" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 16C5 13.5 7.23858 11.5 10 11.5C12.7614 11.5 15 13.5 15 16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),

  // OfferLetters
  'draft': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  ),
  'generate': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="5" y="4" width="10" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 8H12M8 11H12M8 14H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'send': ({ className }) => (
    <svg className={className} width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M16 5L4 10L10 11L11 17L16 5Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // ERCopilot
  'intake': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 6H16M4 10H16M4 14H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  ),
  'analysis': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 16H17M3 12L7 8M7 8L11 12M11 12L15 8M15 8V3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'resolution': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 9.5L9 12.5L14 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'closeout': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 10L9 13L14 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // Policies
  'editor': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 4H17V16H3Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 4L3 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'publish': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 10L8 14L16 6M10 2V18M2 10H18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'acknowledge': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 10L8 12L14 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // OnboardingCenter
  'setup': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 7V10L12 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'documents': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="4" y="4" width="12" height="12" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 8H14M6 11H14M6 14H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'training': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 6L10 3L16 6V12L10 15L4 12V6Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // PTOManagement
  'allocate': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 4V2M13 4V2M3 8H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'request': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 3V17M3 10H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'approve': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 10L8 12L14 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // IRList
  'report': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 2H16V18H4Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 6H13M7 10H13M7 14H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'investigate': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 12L18 18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'resolve': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 10L9 13L15 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // Experience
  'launch': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 17L17 3M17 3H8M17 3V12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'collect': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 10L8 14L16 6M10 2V18M2 10H18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'analyze': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 16H17M4 12L7 8M7 8L10 12M10 12L13 8M13 8L16 12M16 12V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  // Additional icons for remaining workflows
  'evidence': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 3H16V17H4Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 7H14M6 10H14M6 13H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'guidance': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 17C13.866 17 17 13.866 17 10C17 6.13401 13.866 3 10 3C6.13401 3 3 6.13401 3 10C3 13.866 6.13401 17 10 17Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 7V10L12 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'decision': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 2L17 7V13L10 18L3 13V7L10 2Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'action': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 3V17M3 10H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'review': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 6V10L13 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'activate': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="10" cy="10" r="3" fill="currentColor" />
    </svg>
  ),
  'employee': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 16C4 13.5 7 12 10 12C13 12 16 13.5 16 16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'accepted': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 10L8 12L14 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'in_progress': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 6V10L13 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'complete': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 10L7 14L17 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'ready': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 6L10 13L17 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'policy': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 3H16V17H4Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 7H14M6 11H14M6 15H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'calendar': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="12" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 4V2M13 4V2M3 8H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'balance': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 16H17M10 2L4 6V16H16V6L10 2Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'categorize': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="6" height="6" stroke="currentColor" strokeWidth="1.6" />
      <rect x="11" y="3" width="6" height="6" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="11" width="6" height="6" stroke="currentColor" strokeWidth="1.6" />
      <rect x="11" y="11" width="6" height="6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  ),
  'score': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 16H16M4 12L7 8M7 8L10 12M10 12L13 8M13 8L16 12M16 12V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'template': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 3H16V17H4Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 7H14M6 10H14M6 13H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'self': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 16C4 13.5 7 12 10 12C13 12 16 13.5 16 16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'manager': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="7" cy="5" r="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="13" cy="5" r="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 8C5 6.5 6 6 7 6C8 6 9 6.5 9 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M11 8C11 6.5 12 6 13 6C14 6 15 6.5 15 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M5 14V16M15 14V16M10 14V16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'finalize': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 10L7 14L17 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  'config': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 4V2M10 18V16M16 10H18M2 10H4M14.5 5.5L16 4M4 16L5.5 14.5M14.5 14.5L16 16M4 4L5.5 5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  'broadcast': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M2 10C4 13 7 15 10 15C13 15 16 13 18 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M3 6C6 10 8 12 10 12C12 12 14 10 17 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="10" r="1.5" fill="currentColor" />
    </svg>
  ),
  'capture': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="10" cy="10" r="3" fill="currentColor" />
    </svg>
  ),
  'trends': ({ className }) => (
    <svg className={className} width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 16H17M4 12L7 8M7 8L10 12M10 12L13 8M13 8L16 12M16 12V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

const LT = {
  container: 'border border-stone-200 bg-stone-100/80 rounded-2xl overflow-hidden mb-8 shadow-sm',
  headerBtn: 'w-full flex items-center justify-between px-5 py-4 text-left hover:bg-stone-200/50 transition-colors',
  title: 'text-[10px] font-bold uppercase tracking-[0.2em] text-stone-500 font-mono',
  stageBadge: 'px-2 py-0.5 text-[9px] font-mono font-bold uppercase tracking-widest bg-stone-200 border border-stone-300 text-zinc-900',
  stageTitle: 'text-[10px] font-bold uppercase tracking-widest text-stone-600',
  chevron: 'text-stone-400',
  contentBorder: 'border-t border-stone-200',
  stepCircleComplete: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600',
  stepCircleActive: 'bg-zinc-900 border-zinc-900 text-zinc-50 shadow-md',
  stepCirclePending: 'bg-stone-200 border-stone-300 text-stone-400',
  stepTitleActive: 'text-zinc-900',
  stepTitleComplete: 'text-emerald-600/80',
  stepTitlePending: 'text-stone-400',
  connectorActive: 'bg-emerald-500/20',
  connectorPending: 'bg-stone-200',
  infoBox: 'p-5 bg-stone-200/50 border border-stone-200 rounded-xl',
  infoIcon: 'p-2 bg-stone-300 rounded-lg text-stone-600',
  infoTitle: 'text-[11px] font-bold text-zinc-900 uppercase tracking-widest',
  infoBadge: 'text-[8px] px-2 py-0.5 font-bold uppercase tracking-widest bg-emerald-500/10 text-emerald-700 border border-emerald-500/20 rounded-full',
  infoDesc: 'text-xs text-stone-600 leading-relaxed',
  infoAction: 'text-[10px] text-stone-500 font-mono mt-3',
  actionArrow: 'text-emerald-600',
} as const;

const DK = {
  container: 'border border-white/10 bg-zinc-900/50 rounded-2xl overflow-hidden mb-8 shadow-sm backdrop-blur-sm',
  headerBtn: 'w-full flex items-center justify-between px-5 py-4 text-left hover:bg-white/[0.03] transition-colors',
  title: 'text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500 font-mono',
  stageBadge: 'px-2 py-0.5 text-[9px] font-mono font-bold uppercase tracking-widest bg-zinc-800 border border-white/5 text-zinc-100',
  stageTitle: 'text-[10px] font-bold uppercase tracking-widest text-zinc-400',
  chevron: 'text-zinc-600',
  contentBorder: 'border-t border-white/5',
  stepCircleComplete: 'bg-matcha-500/10 border-matcha-500/30 text-matcha-500',
  stepCircleActive: 'bg-white border-white text-black shadow-[0_0_15px_rgba(255,255,255,0.1)]',
  stepCirclePending: 'bg-zinc-900 border-white/5 text-zinc-700',
  stepTitleActive: 'text-white',
  stepTitleComplete: 'text-matcha-500/60',
  stepTitlePending: 'text-zinc-700',
  connectorActive: 'bg-matcha-500/20',
  connectorPending: 'bg-white/5',
  infoBox: 'p-5 bg-zinc-950/40 border border-white/5 rounded-xl',
  infoIcon: 'p-2 bg-white/5 rounded-lg text-zinc-400',
  infoTitle: 'text-[11px] font-bold text-white uppercase tracking-widest',
  infoBadge: 'text-[8px] px-2 py-0.5 font-bold uppercase tracking-widest bg-matcha-500/10 text-matcha-500 border border-matcha-500/20 rounded-full',
  infoDesc: 'text-xs text-zinc-500 leading-relaxed',
  infoAction: 'text-[10px] text-zinc-400 font-mono mt-3',
  actionArrow: 'text-matcha-500',
} as const;

export function LifecycleWizard({
  steps,
  activeStep,
  storageKey,
  title = 'System Lifecycle',
}: LifecycleWizardProps) {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(storageKey) === 'true';
    } catch {
      return false;
    }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(storageKey, String(next));
    } catch {}
  };

  const activeStepData = steps[activeStep - 1] || steps[0];
  const StepIcon = STEP_ICONS[activeStepData.icon];

  return (
    <div className={t.container}>
      <button
        onClick={toggle}
        className={t.headerBtn}
      >
        <div className="flex items-center gap-4">
          <span className={t.title}>
            {title}
          </span>
          <div className="flex items-center gap-2">
            <span className={t.stageBadge}>
              Stage 0{activeStep}
            </span>
            <span className={t.stageTitle + " hidden sm:inline"}>
              {activeStepData.title}
            </span>
          </div>
        </div>
        <ChevronDown
          size={14}
          className={`${t.chevron} transition-transform duration-300 ${collapsed ? '' : 'rotate-180'}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className={`${t.contentBorder} overflow-hidden`}
          >
            <div className="px-5 py-8">
              <div className="flex items-start justify-between gap-8 mb-8 overflow-x-auto no-scrollbar pb-4">
                {steps.map((step, idx) => {
                  const isComplete = step.id < activeStep;
                  const isActive = step.id === activeStep;
                  const StepIconComponent = STEP_ICONS[step.icon];

                  return (
                    <div key={step.id} className="flex items-center gap-4 group flex-shrink-0">
                      <div className="flex flex-col items-center">
                        <div
                          className={`relative w-9 h-9 rounded-full border flex items-center justify-center transition-all duration-500 ${
                            isComplete
                              ? t.stepCircleComplete
                              : isActive
                              ? t.stepCircleActive
                              : t.stepCirclePending
                          }`}
                        >
                          {isComplete ? (
                            <CheckCircle size={16} strokeWidth={2.5} />
                          ) : (
                            <StepIconComponent className="w-4 h-4" />
                          )}
                        </div>
                        <span
                          className={`mt-2 text-[9px] font-bold uppercase tracking-[0.15em] ${
                            isActive ? t.stepTitleActive : isComplete ? t.stepTitleComplete : t.stepTitlePending
                          }`}
                        >
                          {step.title}
                        </span>
                      </div>
                      {idx < steps.length - 1 && (
                        <div
                          className={`w-10 h-px transition-colors duration-700 ${
                            step.id < activeStep ? t.connectorActive : t.connectorPending
                          }`}
                        />
                      )}
                    </div>
                  );
                })}
              </div>

              <div className={t.infoBox}>
                <div className="flex items-start gap-4">
                  <div className={t.infoIcon}>
                    <StepIcon className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <h4 className={t.infoTitle}>
                        {activeStepData.title}
                      </h4>
                      <span className={t.infoBadge}>
                        Active Stage
                      </span>
                    </div>
                    <p className={t.infoDesc}>
                      {activeStepData.description}
                    </p>
                    {activeStepData.action && (
                      <p className={t.infoAction + " opacity-80"}>
                        <span className={t.actionArrow}>→</span> {activeStepData.action}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
