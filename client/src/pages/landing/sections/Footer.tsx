import { Link } from "react-router-dom";
import { fonts } from "../constants";

export const Footer = () => {
  const landingBuildVersion = import.meta.env.VITE_LANDING_BUILD_VERSION || "dev";

  return (
    <footer className="bg-[#0A0E0C] text-[#F0EFEA] pt-32 pb-12 px-6 md:px-16 lg:px-32 relative z-40 border-t border-white/5">
      <div className="max-w-[1600px] mx-auto">
        <h2
          className="text-5xl md:text-8xl font-bold tracking-tighter leading-none mb-16"
          style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
        >
          INITIATE <br />
          <span
            className="italic text-zinc-500 font-light"
            style={{ fontFamily: fonts.serif, letterSpacing: 'normal' }}
          >
            Sequence.
          </span>
        </h2>

        <div className="border-t border-white/10 pt-12 flex justify-between items-center text-[10px] font-mono uppercase tracking-[0.2em] text-[#F0EFEA]/40">
          <div className="flex items-center gap-8">
            <span>© {new Date().getFullYear()} Matcha Architecture</span>
            <Link to="/terms" className="hover:text-white transition-colors">
              Terms
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <span>Build v{landingBuildVersion}</span>
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-[pulse_2s_linear_infinite]" />
            Core Systems Nominal
          </div>
        </div>
      </div>
    </footer>
  );
};
