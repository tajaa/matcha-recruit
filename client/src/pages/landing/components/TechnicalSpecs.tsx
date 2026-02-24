import { motion, AnimatePresence } from "framer-motion";
import { Info, X } from "lucide-react";
import { useState } from "react";

interface TechnicalSpecsProps {
  title: string;
  specs: string[];
}

export const TechnicalSpecs = ({ title, specs }: TechnicalSpecsProps) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative inline-block ml-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="p-2 rounded-full bg-white/5 border border-white/10 text-zinc-500 hover:text-white hover:bg-white/10 transition-colors"
        title="View Technical Specs"
      >
        <Info size={12} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, x: 20, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 20, scale: 0.95 }}
            className="absolute left-full top-0 ml-4 w-64 p-6 bg-zinc-900 border border-white/10 shadow-2xl z-50 rounded-2xl"
          >
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#4ADE80]">
                {title} Specs
              </h4>
              <button onClick={() => setIsOpen(false)} className="text-zinc-500 hover:text-white">
                <X size={12} />
              </button>
            </div>
            <ul className="space-y-3">
              {specs.map((spec, i) => (
                <li key={i} className="text-[10px] text-zinc-400 font-mono leading-relaxed border-l border-white/10 pl-3">
                  {spec}
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
