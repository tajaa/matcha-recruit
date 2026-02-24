import { fonts } from "../constants";

export const Footer = () => {
  return (
    <footer className="bg-[#0A0E0C] text-[#F0EFEA] pt-32 pb-12 px-6 relative z-40 border-t border-white/5">
      <div className="max-w-[1600px] mx-auto">
        <h2
          className="text-5xl md:text-8xl font-bold tracking-tighter leading-none mb-16"
          style={{ fontFamily: fonts.sans }}
        >
          INITIATE <br />
          <span
            className="italic text-[#4ADE80] font-light"
            style={{ fontFamily: fonts.serif }}
          >
            Sequence.
          </span>
        </h2>

        <div className="border-t border-white/10 pt-12 flex justify-between items-center text-[10px] font-mono uppercase tracking-[0.2em] text-[#F0EFEA]/40">
          <span>© {new Date().getFullYear()} Matcha Architecture</span>
          <div className="flex items-center gap-3">
            <span className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-[pulse_2s_linear_infinite]" />
            Core Systems Nominal
          </div>
        </div>
      </div>
    </footer>
  );
};
