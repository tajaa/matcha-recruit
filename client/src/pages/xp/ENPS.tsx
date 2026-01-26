export default function ENPS() {
  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">eNPS Surveys</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Employee Net Promoter Score tracking
        </p>
      </div>

      {/* Coming Soon */}
      <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
        <svg className="w-16 h-16 text-emerald-400 mx-auto mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
        </svg>
        <h3 className="text-2xl font-bold text-white uppercase tracking-wide mb-4">eNPS Survey Management</h3>
        <p className="text-sm text-zinc-400 max-w-2xl mx-auto mb-6">
          The backend API is ready. UI coming soon.
        </p>
        <div className="inline-block px-6 py-3 border border-white/10 bg-zinc-900 rounded">
          <p className="text-xs text-zinc-500 uppercase tracking-wider font-bold mb-2">Available Endpoints:</p>
          <ul className="text-xs text-zinc-400 space-y-1 text-left font-mono">
            <li>POST /api/v1/xp/enps/surveys</li>
            <li>GET /api/v1/xp/enps/surveys</li>
            <li>GET /api/v1/xp/enps/surveys/&#123;id&#125;</li>
            <li>GET /api/v1/xp/enps/surveys/&#123;id&#125;/results</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
