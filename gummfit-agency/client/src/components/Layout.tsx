import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  DollarSign,
  Receipt,
  Link2,
  Briefcase,
  FileText,
  FileCheck,
  Users,
  Search,
  ClipboardList,
  Target,
  Shield,
  UserPlus,
  Image,
  LogOut,
  Menu,
  X,
  ChevronDown,
  Megaphone,
  Gift,
} from 'lucide-react';
import { api } from '../api/client';

interface UserProfile {
  id: number;
  email: string;
  full_name: string;
  role: string;
}

const creatorNav = [
  { to: '/app/gumfit', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/app/gumfit/revenue', icon: DollarSign, label: 'Revenue' },
  { to: '/app/gumfit/expenses', icon: Receipt, label: 'Expenses' },
  { to: '/app/gumfit/platforms', icon: Link2, label: 'Platforms' },
  { to: '/app/gumfit/deals', icon: Briefcase, label: 'Deal Marketplace' },
  { to: '/app/gumfit/applications', icon: FileText, label: 'My Applications' },
  { to: '/app/gumfit/contracts', icon: FileCheck, label: 'My Contracts' },
  { to: '/app/gumfit/offers', icon: Gift, label: 'Campaign Offers' },
  { to: '/app/gumfit/affiliates', icon: Megaphone, label: 'Affiliates' },
];

const agencyNav = [
  { to: '/app/gumfit/agency', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/app/gumfit/agency/deals', icon: Briefcase, label: 'Deals' },
  { to: '/app/gumfit/agency/creators', icon: Search, label: 'Discover Creators' },
  { to: '/app/gumfit/agency/applications', icon: ClipboardList, label: 'Applications' },
  { to: '/app/gumfit/agency/contracts', icon: FileCheck, label: 'Contracts' },
  { to: '/app/gumfit/agency/campaigns', icon: Target, label: 'Campaigns' },
];

const adminNav = [
  { to: '/app/gumfit/admin', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/app/gumfit/admin/creators', icon: Users, label: 'Creators' },
  { to: '/app/gumfit/admin/agencies', icon: Shield, label: 'Agencies' },
  { to: '/app/gumfit/admin/users', icon: Users, label: 'Users' },
  { to: '/app/gumfit/admin/invites', icon: UserPlus, label: 'Invites' },
  { to: '/app/gumfit/admin/assets', icon: Image, label: 'Assets' },
];

function getNavForRole(role: string) {
  switch (role) {
    case 'creator':
      return creatorNav;
    case 'agency':
      return agencyNav;
    case 'gumfit_admin':
      return adminNav;
    default:
      return creatorNav;
  }
}

function getRoleLabel(role: string) {
  switch (role) {
    case 'creator':
      return 'Creator Hub';
    case 'agency':
      return 'Agency Portal';
    case 'gumfit_admin':
      return 'GumFit Admin';
    default:
      return 'GumFit';
  }
}

export function Layout() {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('gummfit_access_token');
    if (!token) {
      navigate('/login');
      return;
    }

    api.auth.me()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem('gummfit_access_token');
        localStorage.removeItem('gummfit_refresh_token');
        navigate('/login');
      });
  }, [navigate]);

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      // ignore
    }
    localStorage.removeItem('gummfit_access_token');
    localStorage.removeItem('gummfit_refresh_token');
    navigate('/login');
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const navItems = getNavForRole(user.role);

  return (
    <div className="min-h-screen flex">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col transform transition-transform lg:transform-none ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-zinc-800">
          <span className="text-xl font-bold text-matcha-500">GumFit</span>
          <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">
            {getRoleLabel(user.role)}
          </span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-zinc-400 hover:text-zinc-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-matcha-600/20 text-matcha-400'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
                }`
              }
            >
              <item.icon className="w-4 h-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User section */}
        <div className="border-t border-zinc-800 p-3">
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-matcha-600/20 text-matcha-400 flex items-center justify-center text-xs font-bold">
                {user.full_name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 text-left min-w-0">
                <div className="truncate font-medium">{user.full_name}</div>
                <div className="truncate text-xs text-zinc-500">{user.email}</div>
              </div>
              <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            {userMenuOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-1 bg-zinc-800 border border-zinc-700 rounded-lg overflow-hidden shadow-lg">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:bg-zinc-700 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header className="lg:hidden h-16 flex items-center px-4 border-b border-zinc-800 bg-zinc-900">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-zinc-400 hover:text-zinc-300"
          >
            <Menu className="w-6 h-6" />
          </button>
          <span className="ml-4 text-lg font-bold text-matcha-500">GumFit</span>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
