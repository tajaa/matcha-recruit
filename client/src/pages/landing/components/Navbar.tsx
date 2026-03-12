import { Link } from "react-router-dom";
import { fonts } from "../constants";

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
        className={`w-full pointer-events-auto flex items-center justify-between px-6 py-1.5 transition-all duration-500 border-b ${
          scrolled
            ? "bg-zinc-900/60 backdrop-blur-xl border-white/10 shadow-[0_4px_30px_rgba(0,0,0,0.2)]"
            : "bg-zinc-900/30 backdrop-blur-sm border-transparent"
        }`}
      >
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-4 group">
            {/* Minimalist Geometric Logo */}
            <div className="relative w-5 h-5 flex items-center justify-center">
               <div className="absolute inset-0 border border-white/50 rotate-45 group-hover:rotate-90 group-hover:border-white transition-all duration-500" />
               <div className="w-1.5 h-1.5 bg-white" />
            </div>
            <span
              className="text-base font-bold tracking-[0.2em] uppercase text-white"
              style={{ fontFamily: fonts.display }}
            >
              Matcha
            </span>
          </Link>
          
          <div className="hidden lg:flex items-center gap-4 pl-8 border-l border-white/10 h-6">
            <div className="w-2 h-2 bg-white/80 animate-pulse" />
            <span className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-400">
              Active Module // <span className="text-white">{activeSection}</span>
            </span>
          </div>
        </div>
        
        <div className="hidden md:flex items-center gap-10">
          <div className="flex gap-10 text-sm font-mono uppercase tracking-[0.2em] text-zinc-300">
            <button
              onClick={onPricingClick}
              className="hover:text-white transition-colors uppercase tracking-[0.2em]"
            >
              Pricing
            </button>
          </div>
          
          <div className="w-px h-6 bg-white/10" />

          <Link
            to="/login"
            className="group relative px-6 py-2 bg-white/10 border border-white/20 text-sm font-mono uppercase tracking-[0.2em] text-white hover:border-white/50 transition-all duration-300 overflow-hidden"
          >
            <span className="relative z-10 font-bold group-hover:text-zinc-900 transition-colors duration-300">Login</span>
            <div className="absolute inset-0 bg-white translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
          </Link>
        </div>
      </div>
    </nav>
  );
};