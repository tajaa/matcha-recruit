import { memo, useEffect, useState } from "react";
import { fonts, LOCAL_JURISDICTIONS } from "../constants";

export const JurisdictionRows = memo(function JurisdictionRows() {
  const [jurisdictionIndex, setJurisdictionIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setJurisdictionIndex((prev) => (prev + 1) % LOCAL_JURISDICTIONS.length);
    }, 4000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between p-4 bg-white/[0.03] rounded-[1rem] border border-white/5">
        <span
          className="text-xs font-medium text-[#F0EFEA] tracking-wide"
          style={{ fontFamily: fonts.sans }}
        >
          Minimum Wage
        </span>
        <span className="px-3 py-1 rounded-md bg-white/5 text-[#4ADE80] text-[9px] font-mono uppercase tracking-[0.2em] border border-[#4ADE80]/20">
          {LOCAL_JURISDICTIONS[jurisdictionIndex]}
        </span>
      </div>
      <div className="flex items-center justify-between p-4 bg-white/[0.03] rounded-[1rem] border border-white/5">
        <span
          className="text-xs font-medium text-[#F0EFEA] tracking-wide"
          style={{ fontFamily: fonts.sans }}
        >
          Predictive Scheduling
        </span>
        <span className="px-3 py-1 rounded-md bg-white/5 text-[#4ADE80] text-[9px] font-mono uppercase tracking-[0.2em] border border-[#4ADE80]/20">
          San Francisco City
        </span>
      </div>
    </div>
  );
});
