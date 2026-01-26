export default function XPDashboard() {
  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Employee Experience</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Monitor engagement, culture, and performance
        </p>
      </div>

      {/* Coming Soon Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Vibe Checks Card */}
        <div className="bg-zinc-900/50 border border-white/10 p-6">
          <div className="flex items-center gap-3 mb-4">
            <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="text-lg font-bold text-white uppercase tracking-wide">Vibe Checks</h3>
          </div>
          <p className="text-sm text-zinc-400 mb-6">
            Quick pulse surveys to measure team mood and engagement in real-time.
          </p>
          <a href="/app/xp/vibe-checks" className="inline-block px-4 py-2 border border-white/10 text-xs font-bold uppercase tracking-wider text-zinc-300 hover:text-white hover:border-white/20 transition-colors">
            Configure
          </a>
        </div>

        {/* eNPS Card */}
        <div className="bg-zinc-900/50 border border-white/10 p-6">
          <div className="flex items-center gap-3 mb-4">
            <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
            <h3 className="text-lg font-bold text-white uppercase tracking-wide">eNPS Surveys</h3>
          </div>
          <p className="text-sm text-zinc-400 mb-6">
            Measure employee Net Promoter Score to track company culture and loyalty.
          </p>
          <a href="/app/xp/enps" className="inline-block px-4 py-2 border border-white/10 text-xs font-bold uppercase tracking-wider text-zinc-300 hover:text-white hover:border-white/20 transition-colors">
            Manage Surveys
          </a>
        </div>

        {/* Performance Reviews Card */}
        <div className="bg-zinc-900/50 border border-white/10 p-6">
          <div className="flex items-center gap-3 mb-4">
            <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <h3 className="text-lg font-bold text-white uppercase tracking-wide">Performance Reviews</h3>
          </div>
          <p className="text-sm text-zinc-400 mb-6">
            Structured review cycles with templates for feedback and goal setting.
          </p>
          <a href="/app/xp/reviews" className="inline-block px-4 py-2 border border-white/10 text-xs font-bold uppercase tracking-wider text-zinc-300 hover:text-white hover:border-white/20 transition-colors">
            View Reviews
          </a>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="bg-zinc-900/50 border border-white/10 p-8 text-center">
        <h3 className="text-2xl font-bold text-white uppercase tracking-wide mb-2">Employee Experience Platform</h3>
        <p className="text-sm text-zinc-500 max-w-2xl mx-auto">
          The XP platform is ready. Configure your vibe checks, launch eNPS surveys, and set up performance review cycles from the pages above.
        </p>
      </div>
    </div>
  );
}
