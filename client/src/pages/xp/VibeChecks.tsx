export default function VibeChecks() {
  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Vibe Checks</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Quick pulse surveys to measure team mood
        </p>
      </div>

      {/* Coming Soon */}
      <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
        <svg className="w-16 h-16 text-emerald-400 mx-auto mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h3 className="text-2xl font-bold text-white uppercase tracking-wide mb-4">Vibe Check Configuration</h3>
        <p className="text-sm text-zinc-400 max-w-2xl mx-auto mb-6">
          The backend API is ready. UI coming soon.
        </p>
        <div className="inline-block px-6 py-3 border border-white/10 bg-zinc-900 rounded">
          <p className="text-xs text-zinc-500 uppercase tracking-wider font-bold mb-2">Available Endpoints:</p>
          <ul className="text-xs text-zinc-400 space-y-1 text-left font-mono">
            <li>POST /api/v1/xp/vibe-checks/config</li>
            <li>GET /api/v1/xp/vibe-checks/config</li>
            <li>GET /api/v1/xp/vibe-checks/analytics</li>
            <li>GET /api/v1/xp/vibe-checks/responses</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
