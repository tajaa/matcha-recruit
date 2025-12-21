import { Link } from 'react-router-dom';
import { Button } from '../components';

export function Landing() {
  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative selection:bg-matcha-500 selection:text-black">
      {/* Background Gradients/Effects */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-matcha-500/10 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-500/10 rounded-full blur-[120px]" />
        <div className="absolute top-[20%] left-[20%] w-full h-px bg-gradient-to-r from-transparent via-white/5 to-transparent rotate-45" />
      </div>

      {/* Navigation */}
      <nav className="relative z-10 flex items-center justify-between px-6 py-6 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-matcha-500 flex items-center justify-center text-zinc-950 font-bold text-lg">
            M
          </div>
          <span className="text-xl font-bold tracking-tight">Matcha Recruit</span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/login" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">
            Log in
          </Link>
          <Link to="/register">
            <Button variant="primary" size="sm" className="bg-white text-black hover:bg-zinc-200 border-none">
              Get Started
            </Button>
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="relative z-10 pt-20 pb-32 px-6 max-w-7xl mx-auto flex flex-col items-center text-center">
        <div className="inline-flex items-center px-3 py-1 rounded-full border border-matcha-500/30 bg-matcha-500/5 text-matcha-400 text-xs font-mono mb-8 uppercase tracking-widest animate-pulse">
          System Online • v2.0.4
        </div>
        
        <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter mb-8 bg-clip-text text-transparent bg-gradient-to-b from-white via-white to-zinc-500">
          The Human Element <br />
          <span className="text-white">Decoded by AI.</span>
        </h1>
        
        <p className="max-w-2xl text-lg md:text-xl text-zinc-400 mb-12 leading-relaxed">
          Conduct thousands of in-depth voice interviews simultaneously. 
          Our autonomous agents analyze tone, context, and capability to find your perfect match.
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-4">
          <Link to="/register">
            <Button size="lg" className="h-14 px-8 text-lg bg-matcha-500 hover:bg-matcha-400 text-black border-none font-bold">
              Initiate Protocol
            </Button>
          </Link>
          <Link to="/login">
            <Button size="lg" variant="outline" className="h-14 px-8 text-lg border-white/20 hover:bg-white/5">
              Live Demo
            </Button>
          </Link>
        </div>

        {/* Visual Element - "The Brain" */}
        <div className="mt-24 relative w-full max-w-4xl aspect-[2/1]">
          <div className="absolute inset-0 bg-gradient-to-b from-matcha-500/5 to-transparent rounded-t-full border-t border-l border-r border-matcha-500/20 backdrop-blur-sm" />
          
          {/* Grid lines */}
          <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:linear-gradient(to_bottom,black,transparent)]" />
          
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 w-64 h-64 bg-matcha-500/20 blur-[80px] rounded-full" />
          
          {/* Mock UI Interface */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/3 w-[80%] h-[80%] border border-white/10 rounded-lg bg-zinc-900/80 backdrop-blur-xl shadow-2xl p-4 flex flex-col gap-4">
             <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <div className="flex gap-2">
                   <div className="w-3 h-3 rounded-full bg-red-500/50" />
                   <div className="w-3 h-3 rounded-full bg-yellow-500/50" />
                   <div className="w-3 h-3 rounded-full bg-green-500/50" />
                </div>
                <div className="text-xs text-zinc-500 font-mono">analysis_module.exe</div>
             </div>
             
             <div className="flex-1 flex gap-4">
                <div className="w-1/3 border-r border-white/5 pr-4 space-y-3">
                   <div className="h-2 w-2/3 bg-zinc-800 rounded animate-pulse" />
                   <div className="h-2 w-1/2 bg-zinc-800 rounded animate-pulse delay-75" />
                   <div className="h-2 w-3/4 bg-zinc-800 rounded animate-pulse delay-150" />
                   
                   <div className="mt-8 p-3 bg-zinc-800/50 rounded border border-white/5">
                      <div className="text-xs text-matcha-400 font-mono mb-1">CANDIDATE SCORE</div>
                      <div className="text-2xl font-bold text-white">94.2%</div>
                   </div>
                </div>
                
                <div className="flex-1 space-y-4">
                   <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center text-xs">AI</div>
                      <div className="bg-zinc-800/50 rounded-lg rounded-tl-none p-3 text-sm text-zinc-300">
                         Can you describe a time you had to optimize a complex distributed system?
                      </div>
                   </div>
                   <div className="flex items-start gap-3 flex-row-reverse">
                      <div className="w-8 h-8 rounded-full bg-matcha-500/20 text-matcha-400 flex items-center justify-center text-xs border border-matcha-500/30">JD</div>
                      <div className="bg-matcha-500/10 border border-matcha-500/10 rounded-lg rounded-tr-none p-3 text-sm text-zinc-200">
                         In my last role at TechCorp, we were facing high latency... I implemented a sharding strategy...
                      </div>
                   </div>
                   
                   <div className="flex gap-1 items-center mt-4">
                      <div className="h-1 w-1 bg-matcha-500 rounded-full animate-bounce" />
                      <div className="h-1 w-1 bg-matcha-500 rounded-full animate-bounce delay-100" />
                      <div className="h-1 w-1 bg-matcha-500 rounded-full animate-bounce delay-200" />
                   </div>
                </div>
             </div>
          </div>
        </div>
      </main>

      {/* Features Grid */}
      <section className="relative z-10 py-24 bg-zinc-900/50 border-t border-white/5">
         <div className="max-w-7xl mx-auto px-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
               {[
                  { title: "Voice Analysis", desc: "Beyond keywords. We analyze sentiment, confidence, and hesitation." },
                  { title: "Bias Elimination", desc: "Standardized interview protocols ensure every candidate gets a fair shot." },
                  { title: "Instant Scaling", desc: "Interview 1 or 10,000 candidates simultaneously with zero scheduling conflicts." }
               ].map((f, i) => (
                  <div key={i} className="p-6 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-colors group">
                     <h3 className="text-xl font-bold text-white mb-3 group-hover:text-matcha-400 transition-colors">{f.title}</h3>
                     <p className="text-zinc-400 leading-relaxed">{f.desc}</p>
                  </div>
               ))}
            </div>
         </div>
      </section>
      
      <footer className="relative z-10 py-12 border-t border-white/5 text-center text-zinc-600 text-sm">
         <p>&copy; {new Date().getFullYear()} Matcha Recruit. All systems nominal.</p>
      </footer>
    </div>
  );
}
