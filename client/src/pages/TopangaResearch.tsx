import { Link } from 'react-router-dom';

const WORKFLOW_CARDS = [
  {
    index: '01',
    title: 'Contextual Understanding',
    description:
      'Every interaction begins with full organizational context — company profile, jurisdiction, employee roster, and conversation history — injected as structured system prompts. The model never starts cold.',
  },
  {
    index: '02',
    title: 'Skill Detection & Routing',
    description:
      'Natural language is parsed into structured skills — offer letters, performance reviews, onboarding flows, policy documents — with confidence scoring that determines whether to act, clarify, or escalate.',
  },
  {
    index: '03',
    title: 'Multi-Step Orchestration',
    description:
      'State machines manage document lifecycle end-to-end: drafting, revision, approval routing, and delivery. Each transition is deterministic, auditable, and reversible.',
  },
  {
    index: '04',
    title: 'Jurisdiction-Aware Compliance',
    description:
      'Federal, state, and local legal baselines are applied automatically based on company headquarters and employee locations. Preemption rules resolve conflicts across overlapping jurisdictions.',
  },
];

const CAPABILITY_CARDS = [
  {
    label: 'Offer Letters',
    detail: 'Generate compensation packages with salary benchmarking, equity structures, and jurisdiction-specific legal language.',
  },
  {
    label: 'Onboarding',
    detail: 'Orchestrate new-hire workflows including provisioning, document collection, and task assignment across teams.',
  },
  {
    label: 'Performance Reviews',
    detail: 'Collect anonymous feedback, generate review summaries, and surface trends across departments.',
  },
  {
    label: 'HR Workbooks',
    detail: 'Draft employee handbooks, policy documents, and compliance reports with structured formatting.',
  },
  {
    label: 'Compliance Monitoring',
    detail: 'Continuous scanning across federal, state, and municipal requirements with automated gap analysis.',
  },
  {
    label: 'AI Chat',
    detail: 'Real-time conversational interface with structured output parsing and document-aware responses.',
  },
];

const PRINCIPLES = [
  {
    title: 'Structured Output',
    description: 'JSON-first document generation — not free-text — for deterministic updates, version control, and downstream system integration.',
  },
  {
    title: 'Context Injection',
    description: 'Company profile, jurisdiction data, and org structure are immutable system prompt parameters. The model operates within your organizational reality.',
  },
  {
    title: 'Sliding-Window History',
    description: 'Conversation context is managed through intelligent windowing — recent exchanges weighted, older context summarized — maintaining coherence across long sessions.',
  },
  {
    title: 'Human-in-the-Loop',
    description: 'Every final action — sending an offer, publishing a policy, modifying a record — requires explicit human approval. The AI drafts. You decide.',
  },
];

export function TopangaResearch() {
  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black">
      {/* Grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #22c55e 1px, transparent 1px),
              linear-gradient(to bottom, #22c55e 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#09090b_70%)]" />
      </div>

      {/* Ambient glow — top center */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-matcha-500/[0.04] rounded-full blur-[120px] pointer-events-none" />

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-matcha-500 shadow-[0_0_10px_rgba(34,197,94,0.8)] group-hover:scale-125 transition-transform" />
          <span className="text-xs tracking-[0.3em] uppercase text-matcha-500 font-medium">
            Topanga Research
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            Matcha
          </Link>
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 border border-zinc-700 px-5 py-2 hover:border-matcha-500 hover:text-matcha-400 transition-all"
          >
            Get Started
          </Link>
        </nav>
      </header>

      <main className="relative z-10">
        {/* ── Hero ── */}
        <section className="container mx-auto px-4 sm:px-8 pt-24 pb-32 max-w-4xl">
          <div className="space-y-8">
            <div className="flex items-center gap-3">
              <span className="h-px w-8 bg-matcha-500/60" />
              <span className="text-[10px] tracking-[0.3em] uppercase text-matcha-500/80">
                Research &middot; Infrastructure &middot; Intelligence
              </span>
            </div>

            <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-white leading-[1.15]">
              State-of-the-Science
              <br />
              Agentic AI for
              <br />
              <span className="text-matcha-400">Human Resources</span>
            </h1>

            <p className="text-zinc-400 text-base sm:text-lg leading-relaxed max-w-2xl">
              Topanga Research is the AI engine behind Matcha. We build agentic
              workflows that reason through multi-step HR tasks — not simple
              prompt-response, but structured orchestration across compliance,
              documentation, and people operations.
            </p>

            <div className="flex items-center gap-6 pt-2">
              <Link
                to="/register"
                className="inline-flex items-center justify-center px-8 py-3 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors"
              >
                Try Matcha
              </Link>
              <a
                href="#how-it-works"
                className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
              >
                See How It Works &darr;
              </a>
            </div>
          </div>
        </section>

        {/* ── How It Works ── */}
        <section id="how-it-works" className="border-t border-zinc-800/60">
          <div className="container mx-auto px-4 sm:px-8 py-24 max-w-5xl">
            <div className="flex items-center gap-3 mb-16">
              <span className="h-px w-8 bg-zinc-700" />
              <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-500">
                How It Works
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-zinc-800/40">
              {WORKFLOW_CARDS.map((card) => (
                <div
                  key={card.index}
                  className="bg-zinc-950 p-8 sm:p-10 group hover:bg-zinc-900/40 transition-colors"
                >
                  <span className="text-[10px] tracking-[0.2em] text-matcha-500/60 font-medium">
                    {card.index}
                  </span>
                  <h3 className="text-sm sm:text-base font-semibold text-white mt-3 mb-4 tracking-wide">
                    {card.title}
                  </h3>
                  <p className="text-zinc-500 text-sm leading-relaxed group-hover:text-zinc-400 transition-colors">
                    {card.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── What Powers Matcha ── */}
        <section className="border-t border-zinc-800/60">
          <div className="container mx-auto px-4 sm:px-8 py-24 max-w-5xl">
            <div className="flex items-center gap-3 mb-6">
              <span className="h-px w-8 bg-zinc-700" />
              <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-500">
                Capabilities
              </span>
            </div>

            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-16 max-w-xl">
              What Powers Matcha
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {CAPABILITY_CARDS.map((card) => (
                <div
                  key={card.label}
                  className="border border-zinc-800/60 p-6 hover:border-matcha-500/30 transition-colors group"
                >
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-1.5 h-1.5 rounded-full bg-matcha-500/40 group-hover:bg-matcha-500 transition-colors" />
                    <h3 className="text-xs font-semibold tracking-[0.15em] uppercase text-zinc-300 group-hover:text-white transition-colors">
                      {card.label}
                    </h3>
                  </div>
                  <p className="text-zinc-600 text-sm leading-relaxed group-hover:text-zinc-400 transition-colors">
                    {card.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Architecture Principles ── */}
        <section className="border-t border-zinc-800/60">
          <div className="container mx-auto px-4 sm:px-8 py-24 max-w-5xl">
            <div className="flex items-center gap-3 mb-6">
              <span className="h-px w-8 bg-zinc-700" />
              <span className="text-[10px] tracking-[0.3em] uppercase text-zinc-500">
                Design Philosophy
              </span>
            </div>

            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-16 max-w-xl">
              Architecture Principles
            </h2>

            <div className="space-y-0 divide-y divide-zinc-800/60">
              {PRINCIPLES.map((p, i) => (
                <div key={p.title} className="flex gap-6 sm:gap-10 py-8 first:pt-0 last:pb-0">
                  <span className="text-[10px] text-zinc-700 font-medium pt-1 shrink-0 w-6 text-right tabular-nums">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-200 mb-2 tracking-wide">
                      {p.title}
                    </h3>
                    <p className="text-zinc-500 text-sm leading-relaxed max-w-xl">
                      {p.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── CTA ── */}
        <section className="border-t border-zinc-800/60">
          <div className="container mx-auto px-4 sm:px-8 py-24 max-w-4xl text-center">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-4">
              Built for the next era of HR
            </h2>
            <p className="text-zinc-500 text-sm mb-10 max-w-lg mx-auto">
              Topanga Research powers every AI interaction inside Matcha.
              See what agentic HR looks like in practice.
            </p>
            <Link
              to="/register"
              className="inline-flex items-center justify-center px-10 py-3 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors"
            >
              Get Started with Matcha
            </Link>
          </div>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="relative z-10 border-t border-zinc-800/40">
        <div className="container mx-auto px-4 sm:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-1.5 h-1.5 rounded-full bg-matcha-500/60" />
            <span className="text-[10px] tracking-[0.2em] uppercase text-zinc-600">
              Topanga Research &middot; A Matcha Company
            </span>
          </div>
          <div className="flex items-center gap-6">
            <Link
              to="/"
              className="text-[10px] tracking-[0.2em] uppercase text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              Matcha
            </Link>
            <Link
              to="/register"
              className="text-[10px] tracking-[0.2em] uppercase text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              Sign Up
            </Link>
            <span className="text-[10px] text-zinc-800">
              &copy; {new Date().getFullYear()}
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default TopangaResearch;
