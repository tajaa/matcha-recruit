import { memo } from "react";
import { motion } from "framer-motion";
import { Fingerprint } from "lucide-react";
import { POLICY_DOTS } from "../constants";

export const PolicyMatrixScanner = memo(() => {
  return (
    <div className="w-full h-full relative p-8 flex items-center justify-center overflow-hidden">
      <div className="grid grid-cols-10 gap-3 relative z-10">
        {POLICY_DOTS.map((dotIndex) => (
          <div
            key={dotIndex}
            className="w-1.5 h-1.5 rounded-full bg-[#0A0E0C]/10 transition-colors duration-500 hover:bg-[#D95A38]"
          />
        ))}
      </div>
      {/* Scanner Line */}
      <motion.div
        animate={{ y: ["-100%", "500%"] }}
        transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
        className="absolute left-0 right-0 h-[2px] bg-[#D95A38] shadow-[0_0_30px_#D95A38] z-20"
      />
      <Fingerprint
        size={24}
        className="text-[#0A0E0C]/10 absolute bottom-8 left-8"
      />
    </div>
  );
});
