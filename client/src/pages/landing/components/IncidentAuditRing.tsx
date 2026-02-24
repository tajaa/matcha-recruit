import { memo } from "react";
import { ShieldCheck } from "lucide-react";

export const IncidentAuditRing = memo(() => (
  <div className="w-full h-full relative flex items-center justify-center">
    <div className="absolute inset-0 border border-[#F0EFEA]/10 rounded-full scale-[0.6] animate-[ping_4s_cubic-bezier(0,0,0.2,1)_infinite]" />
    <div className="absolute inset-0 border border-[#F0EFEA]/20 rounded-full scale-[0.4] animate-[spin_10s_linear_infinite] border-t-transparent" />
    <div className="absolute inset-0 border border-[#F0EFEA]/30 rounded-full scale-[0.3] animate-[spin_7s_linear_infinite_reverse] border-b-transparent" />
    <div className="w-4 h-4 bg-[#F0EFEA] rounded-full shadow-[0_0_20px_#F0EFEA] animate-pulse relative z-10" />
    <ShieldCheck
      size={24}
      className="text-[#F0EFEA]/30 absolute top-8 right-8"
    />
  </div>
));
