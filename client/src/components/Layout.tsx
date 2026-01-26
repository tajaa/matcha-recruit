import { useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';
import { HelpCircle, X } from 'lucide-react';

interface NavItem {
  path: string;
  label: string;
  roles: UserRole[];
  icon: React.ReactNode;
  betaFeature?: string;
  helpText?: string;
}

interface NavSection {
  title: string;
  roles: UserRole[];
  items: NavItem[];
}

// Organized navigation sections
const navSections: NavSection[] = [
  {
    title: 'Recruiting',
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
      {
        path: '/app/matcha/offer-letters',
        label: 'Offer Letters',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/policies',
        label: 'Policies',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/compliance',
        label: 'Compliance',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/employees',
        label: 'Employees',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
        ),
      },
    ],
  },

  {
    title: 'Practice',
    roles: ['admin', 'candidate'],
    items: [
      {
        path: '/app/tutor',
        label: 'Interview Prep',
        roles: ['admin'],
        betaFeature: 'interview_prep',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 14l9-5-9-5-9 5 9 5z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222" />
          </svg>
        ),
      },
      {
        path: '/app/admin/tutor-metrics',
        label: 'Tutor Metrics',
        roles: ['admin'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        path: '/app/admin/test-bot',
        label: 'Test Bot',
        roles: ['admin'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'Employee Experience',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app/xp/dashboard',
        label: 'XP Dashboard',
        roles: ['admin', 'client'],
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
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'HR Tools',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app/matcha/er-copilot',
        label: 'ER Copilot',
        roles: ['admin', 'client'],
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
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        ),
      },
      {
        path: '/app/import',
        label: 'Import',
        roles: ['admin'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        ),
      },
      {
        path: '/app/admin/interview-prep',
        label: 'Interview Prep Beta',
        roles: ['admin'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
      {
        path: '/app/matcha/pto',
        label: 'Time Off',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
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
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 4h9l3 3v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 9h8M8 13h8M8 17h5" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'Employee Portal',
    roles: ['employee'],
    items: [
      {
        path: '/app/portal',
        label: 'Dashboard',
        roles: ['employee'],
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
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
        ),
      },
      {
        path: '/app/portal/documents',
        label: 'My Documents',
        roles: ['employee'],
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
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        ),
      },
      {
        path: '/app/portal/profile',
        label: 'My Profile',
        roles: ['employee'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'Creator Hub',
    roles: ['creator'],
    items: [
      {
        path: '/app/gumfit',
        label: 'Dashboard',
        roles: ['creator'],
        helpText: 'Your central hub showing earnings overview, active deals, and quick actions.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/offers',
        label: 'Campaign Offers',
        roles: ['creator'],
        helpText: 'View and respond to campaign offers from agencies. Accept, decline, or counter-offer with your own rate.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/deals',
        label: 'Browse Deals',
        roles: ['creator'],
        helpText: 'Discover open brand deals and sponsorship opportunities. Apply to campaigns that match your audience.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/applications',
        label: 'My Applications',
        roles: ['creator'],
        helpText: 'Track the status of your deal applications. See which ones are pending, approved, or need action.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/contracts',
        label: 'My Contracts',
        roles: ['creator'],
        helpText: 'View and manage your active contracts. Track deliverables, deadlines, and payment status.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/affiliate',
        label: 'Affiliate Links',
        roles: ['creator'],
        helpText: 'Manage your affiliate tracking links. Monitor clicks, conversions, and commission earnings in real-time.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/revenue',
        label: 'Revenue',
        roles: ['creator'],
        helpText: 'Track all your income sources including sponsorships, affiliate earnings, and platform revenue.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/platforms',
        label: 'Platforms',
        roles: ['creator'],
        helpText: 'Connect your social media accounts to automatically sync follower counts and engagement metrics.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'Agency',
    roles: ['agency'],
    items: [
      {
        path: '/app/gumfit/agency',
        label: 'Dashboard',
        roles: ['agency'],
        helpText: 'Overview of your agency activity including active campaigns, pending applications, and recent contracts.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/agency/campaigns',
        label: 'Campaigns',
        roles: ['agency'],
        helpText: 'Create and manage brand campaigns. Set budgets, deliverables, and invite creators to participate.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/agency/deals',
        label: 'Deal Manager',
        roles: ['agency'],
        helpText: 'Create open deals that creators can apply to. Set requirements, compensation, and review applications.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/agency/creators',
        label: 'Find Creators',
        roles: ['agency'],
        helpText: 'Search and discover creators by niche, follower count, engagement rate, and platform.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/agency/applications',
        label: 'Applications',
        roles: ['agency'],
        helpText: 'Review creator applications for your deals. Approve, reject, or request more information.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/agency/contracts',
        label: 'Contracts',
        roles: ['agency'],
        helpText: 'Manage active contracts with creators. Track deliverables, approve content, and process payments.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
    ],
  },
  {
    title: 'GumFit Admin',
    roles: ['gumfit_admin'],
    items: [
      {
        path: '/app/gumfit/admin',
        label: 'Dashboard',
        roles: ['gumfit_admin'],
        helpText: 'Overview of all GumFit creators, agencies, and platform activity.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/admin/creators',
        label: 'Creators',
        roles: ['gumfit_admin'],
        helpText: 'View and manage all creators on the platform. Review profiles, verify accounts, and track metrics.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/admin/agencies',
        label: 'Agencies',
        roles: ['gumfit_admin'],
        helpText: 'View and manage all agencies. Verify businesses, review profiles, and monitor activity.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/admin/users',
        label: 'Users',
        roles: ['gumfit_admin'],
        helpText: 'Manage all platform users. View accounts, edit permissions, and handle user issues.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/admin/invites',
        label: 'Invites',
        roles: ['gumfit_admin'],
        helpText: 'Send invitations to creators and agencies to join the platform.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        ),
      },
      {
        path: '/app/gumfit/admin/assets',
        label: 'Assets',
        roles: ['gumfit_admin'],
        helpText: 'Manage marketing images and assets for landing pages.',
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
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
  roles: ['admin', 'client', 'candidate', 'employee', 'creator', 'agency', 'gumfit_admin'],
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
  const { user, logout, hasRole, hasBetaFeature } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Check if user can see a nav item (role-based or beta feature access)
  const canSeeItem = (item: NavItem) => {
    // If user has the required role, they can see it
    if (hasRole(...item.roles)) return true;
    // If item has a beta feature requirement and user is a candidate with that feature
    if (item.betaFeature && user?.role === 'candidate' && hasBetaFeature(item.betaFeature)) {
      return true;
    }
    return false;
  };

  // Filter nav items based on user role or beta access
  const navItems = allNavItems.filter(canSeeItem);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const [activeHelp, setActiveHelp] = useState<string | null>(null);

  const NavLink = ({ item }: { item: NavItem }) => {
    const isActive = location.pathname === item.path;
    const showingHelp = activeHelp === item.path;

    return (
      <div className="relative group">
        <div className="flex items-center">
          <Link
            to={item.path}
            className={`flex-1 flex items-center gap-3 px-3 py-2 text-[10px] tracking-[0.15em] uppercase transition-all ${isActive
                ? 'text-white bg-zinc-800 border-l-2 border-white'
                : 'text-zinc-500 hover:text-zinc-300 border-l-2 border-transparent hover:border-zinc-700'
              }`}
          >
            {item.icon}
            <span>{item.label}</span>
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
    <div className="min-h-screen bg-zinc-950 text-zinc-400 font-sans selection:bg-white selection:text-black">
      {/* Noise Overlay */}
      <div className="fixed inset-0 pointer-events-none z-50 bg-noise opacity-30 mix-blend-overlay" />

      {/* Desktop Sidebar - hidden on mobile */}
      <aside className="hidden md:flex fixed top-0 left-0 bottom-0 z-40 w-56 flex-col bg-zinc-950 border-r border-white/10">
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-white/10">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-3 h-3 bg-white flex items-center justify-center">
               <div className="w-1 h-1 bg-black group-hover:scale-0 transition-transform" />
            </div>
            <span className="text-xs tracking-[0.25em] uppercase text-white font-bold group-hover:text-zinc-300 transition-colors">
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
                return (
                  <div key={section.title}>
                    <div className="px-3 mb-3 text-[9px] tracking-[0.2em] uppercase text-zinc-600 font-bold">
                      {section.title}
                    </div>
                    <div className="space-y-1">
                      {visibleItems.map((item) => (
                        <NavLink key={item.path} item={item} />
                      ))}
                    </div>
                  </div>
                );
              })}
          </div>
        </nav>

        {/* Bottom section - Settings & User */}
        <div className="border-t border-white/10 p-4">
          <NavLink item={settingsItem} />
          <div className="mt-4 px-3 py-3 bg-zinc-900 border border-white/5">
            <div className="text-[10px] text-white tracking-wide truncate font-mono">{user?.email}</div>
            <div className="flex items-center justify-between mt-2">
              <span className="px-1.5 py-0.5 text-[8px] bg-emerald-900/30 text-emerald-400 border border-emerald-500/20 tracking-[0.15em] uppercase">
                {user?.role}
              </span>
              <button
                onClick={handleLogout}
                className="text-[9px] tracking-[0.1em] uppercase text-zinc-500 hover:text-white transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
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
              <div className="flex items-center gap-2">
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
      <main className="relative z-10 md:ml-56 pt-20 md:pt-8 pb-12 px-4 sm:px-8 lg:px-12">
        <div className="max-w-[1600px] mx-auto">
          <Outlet />
        </div>
      </main>

      {/* Bottom status bar */}
      <footer className="fixed bottom-0 left-0 md:left-56 right-0 z-30 border-t border-white/5 bg-zinc-950 text-zinc-600">
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