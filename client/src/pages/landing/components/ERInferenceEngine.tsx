import { memo } from "react";
import { motion } from "framer-motion";
import { Database } from "lucide-react";
import { ER_INFERENCE_WIDTHS } from "../constants";

export const ERInferenceEngine = memo(() => (
  <div className="w-full h-full flex flex-col justify-center gap-4 p-8">
    <div className="flex justify-between text-[8px] font-mono text-[#4ADE80]/50 uppercase tracking-widest mb-4">
      <span>Neural Map</span>
      <span className="animate-pulse">Processing</span>
    </div>
    {ER_INFERENCE_WIDTHS.map((width, i) => (
      <div
        key={i}
        className="h-1 w-full bg-white/5 rounded-full overflow-hidden"
      >
        <motion.div
          initial={{ x: "-100%" }}
          animate={{ x: "200%" }}
          transition={{
            duration: 2 + i * 0.5,
            repeat: Infinity,
            ease: "linear",
            delay: i * 0.2,
          }}
          className="h-full bg-[#4ADE80] shadow-[0_0_10px_#4ADE80]"
          style={{ width: `${width * 100}%` }}
        />
      </div>
    ))}
    <Database
      size={24}
      className="text-[#4ADE80]/20 absolute bottom-8 right-8"
    />
  </div>
));
