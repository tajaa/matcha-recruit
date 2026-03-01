import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';
import { HelpCircle, X, ChevronDown, Sliders, Sun, Moon } from 'lucide-react';
import { PendingApproval } from './PendingApproval';
import { PlatformFeatureManager } from '../pages/admin/PlatformFeatureManager';

interface NavItem {
  path: string;
  label: string;
  roles: UserRole[];
  icon: React.ReactNode;
  betaFeature?: string;
  feature?: string;
  anyFeature?: string[];
  helpText?: string;
  platformKey?: string;
}

interface NavSection {
  title: string;
  roles: UserRole[];
  items: NavItem[];
}

// Organized navigation sections
const navSections: NavSection[] = [
  {
    title: 'Core',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app',
        label: 'Dashboard',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Platform',
    roles: ['admin'],
    items: [
      {
        path: '/app/admin/overview',
        label: 'Overview',
        roles: ['admin'],
        platformKey: 'admin_overview',
        helpText: 'View all businesses, employee counts, and platform-wide stats.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        path: '/app/admin/business-registrations',
        label: 'Registrations',
        roles: ['admin'],
        platformKey: 'client_management',
        helpText: 'Review and approve new business account registrations.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
        ),
      },
      {
        path: '/app/admin/company-features',
        label: 'Company Features',
        roles: ['admin'],
        platformKey: 'company_features',
        helpText: 'Toggle features on/off per company.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
          </svg>
        ),
      },
      {
        path: '/app/admin/brokers',
        label: 'Brokers',
        roles: ['admin'],
        helpText: 'Manage brokerage partnerships and their linked client companies.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        ),
      },
      {
        path: '/app/admin/handbooks',
        label: 'Industry Handbooks',
        roles: ['admin'],
        platformKey: 'industry_handbooks',
        helpText: 'Browse and reference industry-standard employee handbooks and culture memos.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        ),
      },
      {
        path: '/app/import',
        label: 'Import',
        roles: ['admin'],
        platformKey: 'admin_import',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Recruiting',
    roles: ['admin', 'client', 'candidate'],
    items: [
      {
        path: '/app/projects',
        label: 'Projects',
        roles: ['admin', 'client'],
        platformKey: 'projects',
        helpText: 'Create recruiting pipelines, add candidates, send interview invites, and track pipeline stages.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7l9 6 9-6" />
          </svg>
        ),
      },
      {
        path: '/app/interviewer',
        label: 'Interviewer',
        roles: ['admin', 'client'],
        platformKey: 'interviewer',
        betaFeature: 'interview_prep',
        helpText: 'Run live AI-powered culture, screening, and candidate-fit interviews.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 14l9-5-9-5-9 5 9 5z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0112 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0112 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222" />
          </svg>
        ),
      },
      {
        path: '/app/admin/candidate-metrics',
        label: 'Candidate Metrics',
        roles: ['admin', 'client'],
        platformKey: 'candidate_metrics',
        feature: 'interview_prep',
        helpText: 'View session results, multi-signal rankings, and send AI-drafted reach-out emails to top candidates.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        path: '/app/admin/interview-prep',
        label: 'Interview Prep Beta',
        roles: ['admin'],
        platformKey: 'interview_prep',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
      {
        path: '/app/admin/test-bot',
        label: 'Test Bot',
        roles: ['admin'],
        platformKey: 'test_bot',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'HR',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app/matcha/onboarding',
        label: 'Onboarding',
        roles: ['admin', 'client'],
        platformKey: 'onboarding',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/employees',
        label: 'Employees',
        roles: ['admin', 'client'],
        platformKey: 'employees',
        feature: 'employees',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/offer-letters',
        label: 'Offer Letters',
        roles: ['admin', 'client'],
        platformKey: 'offer_letters',
        feature: 'offer_letters',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/work',
        label: 'Matcha Work',
        roles: ['admin', 'client'],
        platformKey: 'matcha_work',
        feature: 'matcha_work',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/work/billing',
        label: 'Billing',
        roles: ['admin', 'client'],
        platformKey: 'matcha_work',
        feature: 'matcha_work',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 9V7a5 5 0 00-10 0v2m-2 0h14a1 1 0 011 1v9a2 2 0 01-2 2H6a2 2 0 01-2-2v-9a1 1 0 011-1z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/policies',
        label: 'Policies',
        roles: ['admin', 'client'],
        platformKey: 'policies',
        feature: 'policies',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/handbook',
        label: 'Handbooks',
        roles: ['admin', 'client'],
        platformKey: 'handbooks',
        feature: 'handbooks',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/pto',
        label: 'Time Off',
        roles: ['admin', 'client'],
        platformKey: 'time_off',
        feature: 'time_off',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/leave',
        label: 'Leave Cases',
        roles: ['admin', 'client'],
        platformKey: 'time_off',
        feature: 'time_off',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/accommodations',
        label: 'Accommodations',
        roles: ['admin', 'client'],
        platformKey: 'accommodations',
        feature: 'accommodations',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/internal-mobility',
        label: 'Internal Mobility',
        roles: ['admin', 'client'],
        platformKey: 'internal_mobility',
        feature: 'internal_mobility',
        helpText: 'Publish internal opportunities and review employee applications before talent exits.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7h16M4 12h10M4 17h16" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 12l3 3 5-5" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/er-copilot',
        label: 'ER Copilot',
        roles: ['admin', 'client'],
        platformKey: 'er_copilot',
        feature: 'er_copilot',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
          </svg>
        ),
      },
      {
        path: '/app/ir',
        label: 'Incidents',
        roles: ['admin', 'client'],
        platformKey: 'incidents',
        feature: 'incidents',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/risk-assessment',
        label: 'Risk Assessment',
        roles: ['admin', 'client'],
        platformKey: 'risk_assessment',
        feature: 'risk_assessment',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Employee XP',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app/xp/dashboard',
        label: 'XP Dashboard',
        roles: ['admin', 'client'],
        platformKey: 'xp_dashboard',
        anyFeature: ['vibe_checks', 'enps', 'performance_reviews'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        path: '/app/xp/vibe-checks',
        label: 'Vibe Checks',
        roles: ['admin', 'client'],
        platformKey: 'vibe_checks',
        feature: 'vibe_checks',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
      {
        path: '/app/xp/enps',
        label: 'eNPS Surveys',
        roles: ['admin', 'client'],
        platformKey: 'enps',
        feature: 'enps',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
        ),
      },
      {
        path: '/app/xp/reviews',
        label: 'Performance Reviews',
        roles: ['admin', 'client'],
        platformKey: 'performance_reviews',
        feature: 'performance_reviews',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Compliance',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app/matcha/compliance',
        label: 'Compliance',
        roles: ['admin', 'client'],
        platformKey: 'compliance',
        feature: 'compliance',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
      {
        path: '/app/admin/jurisdictions',
        label: 'Jurisdictions',
        roles: ['admin'],
        platformKey: 'jurisdictions',
        helpText: 'View compliance repository by city & state, manage scheduled checks.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Broker Portal',
    roles: ['broker'],
    items: [
      {
        path: '/app/broker/clients',
        label: 'Client Setups',
        roles: ['broker'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2m-10 2v-2a3 3 0 013-3h4a3 3 0 013 3v2M7 20H2v-2a3 3 0 015.356-1.857M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        ),
      },
      {
        path: '/app/broker/reporting',
        label: 'Reporting',
        roles: ['broker'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-6m3 6V7m3 10v-3m4 5H5a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v12a2 2 0 01-2 2z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Content',
    roles: ['admin'],
    items: [
      {
        path: '/app/admin/blog',
        label: 'Blog',
        roles: ['admin'],
        platformKey: 'blog',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 4h9l3 3v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 9h8M8 13h8M8 17h5" />
          </svg>
        ),
      },
      {
        path: '/app/admin/news',
        label: 'HR News',
        roles: ['admin'],
        platformKey: 'hr_news',
        helpText: 'Browse latest HR industry news from top sources like HR Dive, SHRM, and HR Morning.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 12h10" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'My Workspace',
    roles: ['employee'],
    items: [
      {
        path: '/app/portal',
        label: 'Dashboard',
        roles: ['employee'],
        feature: 'employees',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
      {
        path: '/app/portal/onboarding',
        label: 'Onboarding',
        roles: ['employee'],
        feature: 'employees',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
        ),
      },
      {
        path: '/app/portal/profile',
        label: 'My Profile',
        roles: ['employee'],
        feature: 'employees',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'HR & Benefits',
    roles: ['employee'],
    items: [
      {
        path: '/app/portal/documents',
        label: 'My Documents',
        roles: ['employee'],
        feature: 'employees',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/portal/pto',
        label: 'Time Off',
        roles: ['employee'],
        feature: 'time_off',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/portal/leave',
        label: 'Leave',
        roles: ['employee'],
        feature: 'time_off',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/portal/policies',
        label: 'Policies',
        roles: ['employee'],
        feature: 'policies',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'Culture & Growth',
    roles: ['employee'],
    items: [
      {
        path: '/app/portal/mobility',
        label: 'Mobility',
        roles: ['employee'],
        feature: 'internal_mobility',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7h8M8 12h8M8 17h5" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 15l3 3 5-5" />
          </svg>
        ),
      },
      {
        path: '/app/portal/vibe-check',
        label: 'Vibe Check',
        roles: ['employee'],
        feature: 'vibe_checks',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
      {
        path: '/app/portal/enps',
        label: 'Surveys',
        roles: ['employee'],
        feature: 'enps',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
        ),
      },
      {
        path: '/app/portal/reviews',
        label: 'My Reviews',
        roles: ['employee'],
        feature: 'performance_reviews',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
        ),
      },
    ],
  },
];
// Flatten for mobile menu and legacy compatibility
const allNavItems: NavItem[] = navSections.flatMap(section => section.items);

const settingsItem: NavItem = {
  path: '/app/settings',
  label: 'Settings',
  roles: ['admin', 'client', 'candidate', 'employee', 'broker'],
  icon: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
};

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, profile, logout, hasRole, hasBetaFeature, hasFeature, platformFeatures } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showFeatureManager, setShowFeatureManager] = useState(false);
  const [themeMode, setThemeMode] = useState<'dark' | 'lightSidebar' | 'lightPages'>(() => {
    if (typeof window === 'undefined') return 'lightSidebar';
    const saved = window.localStorage.getItem('matcha_theme_mode');
    if (saved === 'dark' || saved === 'lightSidebar' || saved === 'lightPages') {
      return saved;
    }
    return 'lightSidebar';
  });
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(
    () => new Set(navSections.map(s => s.title))
  );

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('matcha_theme_mode', themeMode);
      if (themeMode === 'lightPages') {
        document.documentElement.classList.add('theme-light-pages');
      } else {
        document.documentElement.classList.remove('theme-light-pages');
      }
    }
  }, [themeMode]);

  const isMatchaWork = location.pathname.startsWith('/app/matcha/work');
  const isOnboarding = location.pathname.startsWith('/app/onboarding');
  const isOfferLetters = location.pathname.startsWith('/app/offer-letters');
  const shouldInvertPages = themeMode === 'lightPages' && !isMatchaWork && !isOnboarding && !isOfferLetters;

  const toggleSection = (title: string) => {
    setCollapsedSections(prev => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };

  // Check if client user's company is pending or rejected
  if (user?.role === 'client' && profile) {
    const companyStatus = (profile as { company_status?: string }).company_status;
    const rejectionReason = (profile as { rejection_reason?: string | null }).rejection_reason;
    const companyName = (profile as { company_name?: string }).company_name;

    if (companyStatus === 'pending') {
      return <PendingApproval status="pending" companyName={companyName} />;
    }

    if (companyStatus === 'rejected') {
      return (
        <PendingApproval
          status="rejected"
          companyName={companyName}
          rejectionReason={rejectionReason}
        />
      );
    }
  }

  // Check if user can see a nav item (role-based, beta feature, or company feature access)
  const canSeeItem = (item: NavItem) => {
    // Check role access first
    if (!hasRole(...item.roles)) {
      // Allow candidates with beta features to see specific items
      if (item.betaFeature && user?.role === 'candidate' && hasBetaFeature(item.betaFeature)) {
        return true;
      }
      return false;
    }
    // Platform-level gate — applies to all roles. visible_features is now
    // returned in /auth/me for every role so platformFeatures is always populated.
    if (item.platformKey && platformFeatures.size > 0 && !platformFeatures.has(item.platformKey)) return false;
    // Check company feature flag (admin bypassed inside hasFeature)
    if (item.feature && !hasFeature(item.feature)) return false;
    // Check if any of multiple features is enabled (e.g. XP Dashboard)
    if (item.anyFeature && !item.anyFeature.some(f => hasFeature(f))) return false;
    return true;
  };

  // Filter nav items based on user role or beta access
  const navItems = allNavItems.filter(canSeeItem);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const [activeHelp, setActiveHelp] = useState<string | null>(null);

  // Extract company name from profile (client users have it, admins don't)
  const companyName = profile && 'company_name' in profile
    ? (profile as { company_name: string }).company_name
    : null;

  const NavLink = ({ item }: { item: NavItem }) => {
    const isActive = location.pathname === item.path;
    const showingHelp = activeHelp === item.path;

    return (
      <div className="relative group min-w-0">
        <div className="flex items-center min-w-0">
          <Link
            to={item.path}
            className={`flex-1 min-w-0 flex items-center gap-3 px-3 py-2 text-[10px] tracking-[0.15em] uppercase transition-all ${isActive
                ? 'text-white bg-zinc-800 border-l-2 border-white light:text-black light:bg-white/50 light:backdrop-blur-md light:shadow-[0_4px_12px_rgba(0,0,0,0.05)] light:border-white/60'
                : 'text-zinc-300 hover:text-white border-l-2 border-transparent hover:border-zinc-700 light:text-black/60 light:hover:text-black light:hover:border-black/20'
              }`}
            title={item.label}
          >
            <span className="shrink-0">{item.icon}</span>
            <span className="truncate">{item.label}</span>
          </Link>
          {item.helpText && (
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setActiveHelp(showingHelp ? null : item.path);
              }}
              className="p-1 mr-1 text-zinc-600 hover:text-zinc-400 transition-colors opacity-0 group-hover:opacity-100"
              title="Learn more"
            >
              <HelpCircle className="w-3 h-3" />
            </button>
          )}
        </div>
        {item.helpText && showingHelp && (
          <div className="absolute left-full top-0 ml-2 w-64 p-3 bg-zinc-900 border border-white/10 shadow-xl z-50 animate-in fade-in slide-in-from-left-2 duration-200">
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-widest text-white font-bold">{item.label}</span>
              <button
                onClick={() => setActiveHelp(null)}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">{item.helpText}</p>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-zinc-950 light:bg-[#e4e4e7] text-zinc-400 light:text-black/70 font-sans selection:bg-white selection:text-black light:selection:bg-black light:selection:text-white">
      {/* Noise Overlay */}
      <div className="fixed inset-0 pointer-events-none z-50 bg-noise opacity-30 mix-blend-overlay light:mix-blend-multiply light:opacity-[0.03]" />

      {/* Abstract Glassmorphism Background Blobs (Light mode only) */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 hidden light:block">
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-white/60 blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[70%] h-[70%] rounded-full bg-[#cbd5e1]/60 blur-[140px]" />
        <div className="absolute top-[20%] right-[10%] w-[40%] h-[40%] rounded-full bg-[#e2e8f0]/80 blur-[100px]" />
        <div className="absolute bottom-[20%] left-[10%] w-[30%] h-[30%] rounded-full bg-[#f1f5f9]/80 blur-[100px]" />
      </div>

      {/* Desktop Sidebar - hidden on mobile */}
      <aside className={`hidden md:flex fixed top-0 left-0 bottom-0 z-40 w-56 flex-col bg-zinc-950 light:bg-white/10 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] border-r border-white/10 light:border-white/30 light:shadow-[1px_0_24px_rgba(0,0,0,0.02),inset_-1px_0_0_rgba(255,255,255,0.4)] ${themeMode === 'lightSidebar' ? 'invert brightness-90 hue-rotate-180' : ''}`}>
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-white/10 light:border-black/5">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-3 h-3 bg-white light:bg-black flex items-center justify-center">
               <div className="w-1 h-1 bg-black light:bg-white group-hover:scale-0 transition-transform" />
            </div>
            <span className="text-xs tracking-[0.25em] uppercase text-white light:text-black font-bold group-hover:text-zinc-300 light:group-hover:text-black/70 transition-colors">
              Matcha
            </span>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-6 overflow-y-auto">
          <div className="space-y-6 px-4">
            {navSections
              .filter((section) => hasRole(...section.roles) || section.items.some(canSeeItem))
              .map((section) => {
                const visibleItems = section.items.filter(canSeeItem);
                if (visibleItems.length === 0) return null;
                const isCollapsed = collapsedSections.has(section.title);
                return (
                  <div key={section.title}>
                    <button
                      onClick={() => toggleSection(section.title)}
                      className="w-full flex items-center justify-between px-3 mb-1 text-[9px] tracking-[0.2em] uppercase text-zinc-300 hover:text-white light:text-black/50 light:hover:text-black font-bold transition-colors"
                    >
                      {section.title}
                      <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${isCollapsed ? '-rotate-90' : ''}`} />
                    </button>
                    {!isCollapsed && (
                      <div className="space-y-1 mt-1">
                        {visibleItems.map((item) => (
                          <NavLink key={item.path} item={item} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </nav>

        {/* Bottom section - Settings & User */}
        <div className="border-t border-white/10 light:border-black/5 p-4">
          {user?.role === 'admin' && (
            <button
              onClick={() => setShowFeatureManager(true)}
              className="w-full flex items-center gap-3 px-3 py-2 text-[10px] tracking-[0.15em] uppercase text-zinc-400 hover:text-white light:text-black/60 light:hover:text-black border-l-2 border-transparent hover:border-zinc-700 light:hover:border-black/20 transition-all mb-3"
            >
              <Sliders className="w-4 h-4 shrink-0" />
              <span>Manage Features</span>
            </button>
          )}
          <NavLink item={settingsItem} />
          
          <button
            onClick={() => {
              if (themeMode === 'dark') setThemeMode('lightSidebar');
              else if (themeMode === 'lightSidebar') setThemeMode('lightPages');
              else setThemeMode('dark');
            }}
            className="w-full flex items-center gap-3 px-3 py-2 text-[10px] tracking-[0.15em] uppercase text-zinc-400 hover:text-white light:text-black/60 light:hover:text-black border-l-2 border-transparent hover:border-zinc-700 light:hover:border-black/20 transition-all mt-1"
          >
            {themeMode === 'lightPages' ? <Moon className="w-4 h-4 shrink-0" /> : <Sun className="w-4 h-4 shrink-0" />}
            <span>
              {themeMode === 'dark' ? 'Light Sidebar' : 
               themeMode === 'lightSidebar' ? 'Light Pages' : 
               'Dark Mode'}
            </span>
          </button>

          <div className="mt-4 px-3 py-3 bg-zinc-900 border border-white/5 light:bg-black/[0.03] light:border-black/[0.05] light:shadow-inner">
            {companyName && (
              <div className="text-[10px] font-bold text-white light:text-black tracking-widest uppercase truncate mb-2 pb-2 border-b border-white/10 light:border-black/10">
                {companyName}
              </div>
            )}
            <div className="text-[10px] text-zinc-400 light:text-black/70 tracking-wide truncate font-mono">{user?.email}</div>
            <div className="flex items-center justify-between mt-2">
              <span className="px-1.5 py-0.5 text-[8px] bg-emerald-900/30 text-emerald-400 border border-emerald-500/20 light:bg-black/10 light:text-black light:border-black/10 tracking-[0.15em] uppercase">
                {user?.role}
              </span>
              <button
                onClick={handleLogout}
                className="text-[9px] tracking-[0.1em] uppercase text-zinc-500 hover:text-white light:text-black/50 light:hover:text-black transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
        {showFeatureManager && (
          <PlatformFeatureManager
            onClose={() => setShowFeatureManager(false)}
          />
        )}
      </aside>

      {/* Mobile Header - visible only on mobile */}
      <nav className="md:hidden fixed top-0 inset-x-0 z-50 bg-zinc-950/80 backdrop-blur-md border-b border-white/10">
        <div className="px-4">
          <div className="flex justify-between h-14">
            <div className="flex items-center">
              <Link to="/" className="flex items-center gap-2 group">
                <div className="w-2 h-2 rounded-full bg-white" />
                <span className="text-xs tracking-[0.25em] uppercase text-white font-medium">
                  Matcha
                </span>
              </Link>
            </div>

            {user && (
              <div className="flex items-center gap-3">
                {companyName && (
                  <span className="text-[10px] font-bold text-white uppercase tracking-widest hidden sm:block truncate max-w-[140px]">
                    {companyName}
                  </span>
                )}
                <button
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="p-2 text-zinc-400 hover:text-white transition-colors"
                  aria-label="Toggle menu"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    {mobileMenuOpen ? (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                    ) : (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
                    )}
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Mobile menu dropdown */}
        {mobileMenuOpen && (
          <div className="border-t border-white/10 bg-zinc-950">
            <div className="px-4 py-3 space-y-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 text-[10px] tracking-[0.15em] uppercase transition-all ${location.pathname === item.path
                      ? 'text-white bg-zinc-900 border-l-2 border-white'
                      : 'text-zinc-500 hover:text-white border-l-2 border-transparent hover:border-zinc-800'
                    }`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              ))}
              <div className="pt-3 mt-3 border-t border-white/10">
                <div className="px-3 py-2 text-[10px] text-zinc-400 tracking-wide font-mono">
                  {user?.email}
                  <span className="ml-2 px-2 py-0.5 bg-emerald-900/20 text-emerald-400 border border-emerald-500/20 tracking-[0.15em] uppercase">
                    {user?.role}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    handleLogout();
                  }}
                  className="block w-full text-left px-3 py-2.5 text-[10px] tracking-[0.15em] uppercase text-zinc-500 hover:text-white transition-colors"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* Main content - offset for sidebar on desktop, header on mobile */}
      <main className={`relative z-10 md:ml-56 pt-20 md:pt-6 pb-12 px-4 sm:px-6 lg:px-8 overflow-x-hidden ${shouldInvertPages ? 'invert brightness-90 hue-rotate-180 bg-zinc-950 min-h-screen' : ''}`}>
        <div className="max-w-[1600px] mx-auto">
          <Outlet />
        </div>
      </main>

      {/* Bottom status bar */}
      <footer className={`fixed bottom-0 left-0 md:left-56 right-0 z-30 border-t border-white/5 bg-zinc-950 text-zinc-600 ${shouldInvertPages ? 'invert brightness-90 hue-rotate-180' : ''}`}>
        <div className="px-6 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[9px] tracking-[0.2em] uppercase">
              System Active
            </span>
          </div>
          <span className="text-[9px] tracking-[0.15em] uppercase font-mono">
            v2.4.0
          </span>
        </div>
      </footer>
    </div>
  );
}
