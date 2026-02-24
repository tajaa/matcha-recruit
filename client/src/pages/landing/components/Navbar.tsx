import { Link } from "react-router-dom";

interface NavbarProps {
  scrolled: boolean;
  activeSection: string;
  scrollTo: (ref: React.RefObject<HTMLDivElement | null>) => void;
  manifestoRef: React.RefObject<HTMLDivElement | null>;
  systemRef: React.RefObject<HTMLDivElement | null>;
}

export const Navbar = ({ scrolled, activeSection, scrollTo, manifestoRef, systemRef }: NavbarProps) => {
  return (
    <nav className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-[1600px] pointer-events-none">
      <div
        className={`pointer-events-auto flex items-center justify-between px-6 py-4 rounded-[2rem] transition-all duration-500 border ${
          scrolled
            ? "bg-[#0A0E0C]/80 backdrop-blur-md border-[#F0EFEA]/10 shadow-2xl"
            : "bg-transparent border-transparent"
        }`}
      >
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-full border border-[#F0EFEA]/20 flex items-center justify-center overflow-hidden bg-[#0A0E0C]">
              <div className="w-full h-full bg-[#4ADE80] opacity-0 group-hover:opacity-30 transition-opacity duration-300" />
            </div>
            <span className="font-sans text-sm font-bold tracking-[0.2em] uppercase">
              Matcha
            </span>
          </Link>
          
          <div className="hidden lg:flex items-center gap-3 pl-6 border-l border-white/10">
            <div className="w-1 h-1 bg-[#4ADE80] rounded-full animate-pulse" />
            <span className="text-[8px] font-mono uppercase tracking-[0.3em] text-[#4ADE80]">
              Active Module: {activeSection}
            </span>
          </div>
        </div>
        <div className="hidden md:flex gap-10 text-[10px] font-mono uppercase tracking-[0.2em] text-[#F0EFEA]/60">
          <span
            onClick={() => scrollTo(manifestoRef)}
            className="hover:text-[#4ADE80] cursor-pointer transition-colors"
          >
            Philosophy
          </span>
          <span
            onClick={() => scrollTo(systemRef)}
            className="hover:text-[#4ADE80] cursor-pointer transition-colors"
          >
            System
          </span>
          <span className="text-[#F0EFEA]/35 cursor-default">
            Pricing
          </span>
          <Link to="/terms" className="hover:text-[#4ADE80] transition-colors">
            Terms
          </Link>
        </div>
        <Link
          to="/login"
          className="px-6 py-2.5 rounded-full border border-[#F0EFEA]/20 text-[10px] font-mono uppercase tracking-[0.2em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-colors"
        >
          Login
        </Link>
      </div>
    </nav>
  );
};
