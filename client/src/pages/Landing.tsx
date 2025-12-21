import { Link } from 'react-router-dom';
import { Button } from '../components';

export function Landing() {
  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative selection:bg-matcha-500 selection:text-black font-sans">
      {/* Dynamic Background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        {/* Restored Gradients */}
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-matcha-500/20 rounded-full blur-[120px] opacity-70" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-emerald-500/20 rounded-full blur-[120px] opacity-70" />
        
        {/* Central Pulse */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40vw] h-[40vw] bg-matcha-500/10 rounded-full blur-[100px] animate-pulse" />
        
        {/* Grid Overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#22c55e_1px,transparent_1px),linear-gradient(to_bottom,#22c55e_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-[0.05]" />
        
        {/* Vignette to keep text readable */}
        <div className="absolute inset-0 bg-zinc-950/30" />
      </div>

      {/* Header */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-6 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-matcha-500/20 border border-matcha-500 flex items-center justify-center">
             <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          </div>
          <span className="text-sm font-mono tracking-widest uppercase text-matcha-500">Matcha</span>
        </div>
        <div className="flex items-center gap-6">
          <Link to="/login" className="text-xs font-mono uppercase tracking-widest text-zinc-500 hover:text-matcha-400 transition-colors">
            Login
          </Link>
          <Link to="/register">
             <span className="text-xs font-mono uppercase tracking-widest text-white border border-white/20 px-4 py-2 rounded hover:bg-matcha-500 hover:text-black hover:border-matcha-500 transition-all">
                Initialize
             </span>
          </Link>
        </div>
      </nav>

      {/* Main Content */}
      <main className="relative z-10 flex flex-col items-center justify-center min-h-[80vh] px-4 text-center">
        
        {/* Animated Voice Visualizer */}
        <div className="relative h-24 flex items-center justify-center gap-2 mb-16">
           {[...Array(9)].map((_, i) => (
              <div 
                key={i} 
                className="w-2 bg-matcha-500/80 rounded-full animate-sound-wave shadow-[0_0_15px_rgba(34,197,94,0.5)]"
                style={{
                   height: '20%',
                   animationDelay: `${i * 0.1}s`,
                   animationDuration: '1.2s'
                }} 
              />
           ))}
        </div>

        <h1 className="text-6xl md:text-8xl font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-b from-white via-zinc-200 to-zinc-600 mb-8 max-w-4xl mx-auto">
          We are listening.
        </h1>

        <p className="max-w-xl text-lg text-zinc-400 mb-12 font-light leading-relaxed tracking-wide">
          Advanced autonomous interviewing agents. <br/>
          Analyzing tone, sentiment, and potential.
        </p>

        <div className="flex flex-col sm:flex-row gap-6">
          <Link to="/register">
            <Button size="lg" className="bg-matcha-500 hover:bg-matcha-400 text-black px-12 h-14 text-sm tracking-widest uppercase font-bold shadow-[0_0_30px_-5px_rgba(34,197,94,0.6)] hover:shadow-[0_0_40px_rgba(34,197,94,0.8)] transition-all duration-500">
              Start Interview
            </Button>
          </Link>
        </div>

        <div className="mt-24 flex items-center gap-8 opacity-50">
           <div className="flex flex-col items-center gap-2">
              <span className="text-2xl font-bold text-white">∞</span>
              <span className="text-[10px] uppercase tracking-widest text-zinc-500">Scalability</span>
           </div>
           <div className="w-px h-8 bg-zinc-800" />
           <div className="flex flex-col items-center gap-2">
              <span className="text-2xl font-bold text-white">0s</span>
              <span className="text-[10px] uppercase tracking-widest text-zinc-500">Latency</span>
           </div>
           <div className="w-px h-8 bg-zinc-800" />
           <div className="flex flex-col items-center gap-2">
              <span className="text-2xl font-bold text-white">24/7</span>
              <span className="text-[10px] uppercase tracking-widest text-zinc-500">Active</span>
           </div>
        </div>

      </main>

      <style>{`
        @keyframes sound-wave {
          0%, 100% { height: 20%; opacity: 0.5; }
          50% { height: 100%; opacity: 1; }
        }
        .animate-sound-wave {
          animation-name: sound-wave;
          animation-timing-function: ease-in-out;
          animation-iteration-count: infinite;
        }
      `}</style>
    </div>
  );
}