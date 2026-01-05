import { useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';

interface NavItem {
  path: string;
  label: string;
  roles: UserRole[];
  icon: React.ReactNode;
  betaFeature?: string; // If set, candidates with this beta feature can also see this item
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
        path: '/app/offer-letters',
        label: 'Offer Letters',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        ),
      },
      {
        path: '/app/policies',
        label: 'Policies',
        roles: ['admin', 'client'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
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
        path: '/app/tutor-metrics',
        label: 'Tutor Metrics',
        roles: ['admin'],
        icon: (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
      },
      {
        path: '/app/test-bot',
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
    title: 'HR Tools',
    roles: ['admin', 'client'],
    items: [
      {
        path: '/app/er-copilot',
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
    ],
  },
];

// Flatten for mobile menu and legacy compatibility
const allNavItems: NavItem[] = navSections.flatMap(section => section.items);

const settingsItem: NavItem = {
  path: '/app/settings',
  label: 'Settings',
  roles: ['admin', 'client', 'candidate'],
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

  const NavLink = ({ item }: { item: NavItem }) => {
    const isActive = location.pathname === item.path;
    return (
      <Link
        to={item.path}
        className={`flex items-center gap-3 px-3 py-2 text-[10px] tracking-[0.15em] uppercase transition-all ${isActive
            ? 'text-white bg-zinc-800 border-l-2 border-white'
            : 'text-zinc-500 hover:text-zinc-300 border-l-2 border-transparent hover:border-zinc-700'
          }`}
      >
        {item.icon}
        <span>{item.label}</span>
      </Link>
    );
  };

  return (
    <div className="min-h-screen bg-black text-zinc-400 font-mono">

      {/* Desktop Sidebar - hidden on mobile */}
      <aside className="hidden md:flex fixed top-0 left-0 bottom-0 z-50 w-48 flex-col bg-zinc-950 border-r border-zinc-800">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-zinc-800">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="w-2 h-2 rounded-full bg-white" />
            <span className="text-xs tracking-[0.25em] uppercase text-white font-medium group-hover:text-zinc-300 transition-colors">
              Matcha
            </span>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 overflow-y-auto">
          <div className="space-y-4 px-2">
            {navSections
              .filter((section) => hasRole(...section.roles) || section.items.some(canSeeItem))
              .map((section) => {
                const visibleItems = section.items.filter(canSeeItem);
                if (visibleItems.length === 0) return null;
                return (
                  <div key={section.title}>
                    <div className="px-3 mb-1 text-[8px] tracking-[0.2em] uppercase text-zinc-600 font-medium">
                      {section.title}
                    </div>
                    <div className="space-y-0.5">
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
        <div className="border-t border-zinc-800 p-2">
          <NavLink item={settingsItem} />
          <div className="mt-3 px-3 py-2">
            <div className="text-[9px] text-zinc-600 tracking-wide truncate">{user?.email}</div>
            <div className="flex items-center justify-between mt-1">
              <span className="px-1.5 py-0.5 text-[8px] bg-zinc-800 text-zinc-400 border border-zinc-700 tracking-[0.15em] uppercase">
                {user?.role}
              </span>
              <button
                onClick={handleLogout}
                className="text-[9px] tracking-[0.1em] uppercase text-zinc-600 hover:text-zinc-300 transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Header - visible only on mobile */}
      <nav className="md:hidden fixed top-0 inset-x-0 z-50 bg-zinc-950 border-b border-zinc-800">
        <div className="px-4">
          <div className="flex justify-between h-14">
            <div className="flex items-center">
              <Link to="/" className="flex items-center gap-2 group">
                <div className="w-2 h-2 rounded-full bg-white" />
                <span className="text-xs tracking-[0.25em] uppercase text-white font-medium group-hover:text-zinc-300 transition-colors">
                  Matcha
                </span>
              </Link>
            </div>

            {user && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="p-2 text-zinc-500 hover:text-zinc-300 transition-colors"
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
          <div className="border-t border-zinc-800 bg-zinc-950">
            <div className="px-4 py-3 space-y-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 text-[10px] tracking-[0.15em] uppercase transition-all ${location.pathname === item.path
                      ? 'text-white bg-zinc-800 border-l-2 border-white'
                      : 'text-zinc-500 hover:text-zinc-300 border-l-2 border-transparent hover:border-zinc-700'
                    }`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              ))}
              <Link
                to="/app/settings"
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 text-[10px] tracking-[0.15em] uppercase transition-all ${location.pathname === '/app/settings'
                    ? 'text-white bg-zinc-800 border-l-2 border-white'
                    : 'text-zinc-500 hover:text-zinc-300 border-l-2 border-transparent hover:border-zinc-700'
                  }`}
              >
                {settingsItem.icon}
                <span>Settings</span>
              </Link>
              <div className="pt-3 mt-3 border-t border-zinc-800">
                <div className="px-3 py-2 text-[10px] text-zinc-600 tracking-wide">
                  {user?.email}
                  <span className="ml-2 px-2 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700 tracking-[0.15em] uppercase">
                    {user?.role}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    handleLogout();
                  }}
                  className="block w-full text-left px-3 py-2.5 text-[10px] tracking-[0.15em] uppercase text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* Main content - offset for sidebar on desktop, header on mobile */}
      <main className="relative z-10 md:ml-48 pt-16 md:pt-6 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <Outlet />
        </div>
      </main>

      {/* Bottom status bar */}
      <footer className="fixed bottom-0 left-0 md:left-48 right-0 z-40 border-t border-zinc-800 bg-zinc-950">
        <div className="px-4 sm:px-6 lg:px-8 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-white" />
            <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600">
              Active
            </span>
          </div>
          <span className="text-[9px] tracking-[0.15em] uppercase text-zinc-700">
            v1.0
          </span>
        </div>
      </footer>
    </div>
  );
}
