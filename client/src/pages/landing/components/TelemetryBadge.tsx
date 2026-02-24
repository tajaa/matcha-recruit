import { memo } from "react";

interface TelemetryBadgeProps {
  text: string;
  active?: boolean;
}

export const TelemetryBadge = memo(function TelemetryBadge({
  text,
  active = false,
}: TelemetryBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-[9px] font-mono uppercase tracking-widest transition-colors duration-500
      ${active ? "border-[#4ADE80]/30 bg-[#4ADE80]/10 text-[#4ADE80]" : "border-[#F0EFEA]/10 bg-[#F0EFEA]/5 text-[#F0EFEA]/60"}`}
    >
      {active && (
        <span className="w-1.5 h-1.5 bg-[#4ADE80] rounded-full animate-pulse shadow-[0_0_8px_#4ADE80]" />
      )}
      {text}
    </span>
  );
});
