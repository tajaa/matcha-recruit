export default function PerformanceReviews() {
  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Performance Reviews</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Structured review cycles and feedback
        </p>
      </div>

      {/* Coming Soon */}
      <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
        <svg className="w-16 h-16 text-emerald-400 mx-auto mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        <h3 className="text-2xl font-bold text-white uppercase tracking-wide mb-4">Performance Review System</h3>
        <p className="text-sm text-zinc-400 max-w-2xl mx-auto mb-6">
          The backend API is ready. UI coming soon.
        </p>
        <div className="inline-block px-6 py-3 border border-white/10 bg-zinc-900 rounded">
          <p className="text-xs text-zinc-500 uppercase tracking-wider font-bold mb-2">Available Endpoints:</p>
          <ul className="text-xs text-zinc-400 space-y-1 text-left font-mono">
            <li>POST /api/v1/xp/reviews/templates</li>
            <li>GET /api/v1/xp/reviews/templates</li>
            <li>POST /api/v1/xp/reviews/cycles</li>
            <li>GET /api/v1/xp/reviews/cycles</li>
            <li>GET /api/v1/xp/reviews/cycles/&#123;id&#125;/progress</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
