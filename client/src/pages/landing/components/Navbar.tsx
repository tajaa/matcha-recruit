import { Link } from "react-router-dom";

interface NavbarProps {
  scrolled: boolean;
  activeSection: string;
  scrollTo: (ref: React.RefObject<HTMLDivElement | null>) => void;
  manifestoRef: React.RefObject<HTMLDivElement | null>;
  onPricingClick: () => void;
}

export const Navbar = ({ scrolled, activeSection, scrollTo, manifestoRef, onPricingClick }: NavbarProps) => {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 pointer-events-none transition-all duration-500">
      <div
        className={`w-full pointer-events-auto flex items-center justify-between px-6 py-3 transition-all duration-500 border-b ${
          scrolled
            ? "bg-white/60 backdrop-blur-xl border-black/10 shadow-[0_4px_30px_rgba(0,0,0,0.05)]"
            : "bg-white/25 backdrop-blur-sm border-transparent"
        }`}
      >
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-4 group">
            {/* Minimalist Geometric Logo */}
            <div className="relative w-8 h-8 flex items-center justify-center">
               <div className="absolute inset-0 border border-black/30 rotate-45 group-hover:rotate-90 group-hover:border-black transition-all duration-500" />
               <div className="w-1.5 h-1.5 bg-black" />
            </div>
            <span 
              className="font-mono text-2xl font-bold tracking-[0.3em] uppercase text-zinc-300"
              style={{ WebkitTextStroke: '2px black' }}
            >
              Matcha
            </span>
          </Link>
          
          <div className="hidden lg:flex items-center gap-4 pl-8 border-l border-black/10 h-6">
            <div className="w-2 h-2 bg-black/80 animate-pulse" />
            <span className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
              Active Module // <span className="text-black">{activeSection}</span>
            </span>
          </div>
        </div>
        
        <div className="hidden md:flex items-center gap-10">
          <div className="flex gap-10 text-sm font-mono uppercase tracking-[0.2em] text-zinc-800">
            <button
              onClick={() => scrollTo(manifestoRef)}
              className="hover:text-black transition-colors uppercase tracking-[0.2em]"
            >
              System
            </button>
            <button
              onClick={onPricingClick}
              className="hover:text-black transition-colors uppercase tracking-[0.2em]"
            >
              Pricing
            </button>
          </div>
          
          <div className="w-px h-6 bg-black/10" />
          
          <Link
            to="/login"
            className="group relative px-6 py-2 bg-black/5 border border-black/10 text-sm font-mono uppercase tracking-[0.2em] text-black hover:border-black/30 transition-all duration-300 overflow-hidden"
          >
            <span className="relative z-10 font-bold group-hover:text-white transition-colors duration-300">Login</span>
            <div className="absolute inset-0 bg-black translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
          </Link>
        </div>
      </div>
    </nav>
  );
};