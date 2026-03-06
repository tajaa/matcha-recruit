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
            ? "bg-[#0A0E0C]/90 backdrop-blur-xl border-white/10 shadow-[0_4px_30px_rgba(0,0,0,0.5)]"
            : "bg-transparent border-transparent"
        }`}
      >
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-3 group">
            {/* Minimalist Geometric Logo */}
            <div className="relative w-6 h-6 flex items-center justify-center">
               <div className="absolute inset-0 border border-white/30 rotate-45 group-hover:rotate-90 group-hover:border-white transition-all duration-500" />
               <div className="w-1 h-1 bg-white" />
            </div>
            <span className="font-mono text-xs font-bold tracking-[0.3em] uppercase text-white">
              Matcha
            </span>
          </Link>
          
          <div className="hidden lg:flex items-center gap-3 pl-6 border-l border-white/10 h-4">
            <div className="w-1.5 h-1.5 bg-white/80 animate-pulse" />
            <span className="text-[8px] font-mono uppercase tracking-[0.3em] text-zinc-500">
              Active Module // <span className="text-white">{activeSection}</span>
            </span>
          </div>
        </div>
        
        <div className="hidden md:flex items-center gap-8">
          <div className="flex gap-8 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <button
              onClick={() => scrollTo(manifestoRef)}
              className="hover:text-white transition-colors uppercase tracking-[0.2em]"
            >
              System
            </button>
            <button
              onClick={onPricingClick}
              className="hover:text-white transition-colors uppercase tracking-[0.2em]"
            >
              Pricing
            </button>
          </div>
          
          <div className="w-px h-4 bg-white/10" />
          
          <Link
            to="/login"
            className="group relative px-6 py-2 bg-white/5 border border-white/10 text-[9px] font-mono uppercase tracking-[0.2em] text-white hover:border-white/30 transition-all duration-300 overflow-hidden"
          >
            <span className="relative z-10 font-bold">Terminal Login</span>
            <div className="absolute inset-0 bg-white translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
            <span className="absolute inset-0 flex items-center justify-center text-black font-bold translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out z-20">
              Terminal Login
            </span>
          </Link>
        </div>
      </div>
    </nav>
  );
};
