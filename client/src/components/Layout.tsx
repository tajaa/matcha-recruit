import { Link, Outlet, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/', label: 'Companies' },
  { path: '/positions', label: 'Positions' },
  { path: '/candidates', label: 'Candidates' },
  { path: '/jobs', label: 'Job Search' },
  { path: '/import', label: 'Import' },
];

export function Layout() {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-400 font-sans selection:bg-matcha-500 selection:text-white">
      <nav className="fixed top-0 inset-x-0 z-50 bg-zinc-900/80 backdrop-blur-md border-b border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-8">
              <div className="flex-shrink-0 flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-matcha-500 flex items-center justify-center text-zinc-950 font-bold text-lg">
                  M
                </div>
                <div>
                  <span className="text-xl font-bold text-white tracking-tight">Matcha</span>
                  <span className="text-xl font-light text-zinc-500 ml-1">Recruit</span>
                </div>
              </div>
              <div className="hidden sm:flex sm:space-x-1">
                {navItems.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`inline-flex items-center px-3 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                      location.pathname === item.path
                        ? 'text-matcha-400 bg-matcha-500/10'
                        : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
                    }`}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-12">
        <Outlet />
      </main>
    </div>
  );
}
