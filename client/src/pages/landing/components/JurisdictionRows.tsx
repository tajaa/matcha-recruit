import { memo, useEffect, useState, useRef } from "react";
import { m, AnimatePresence } from "framer-motion";

const LAWS = [
  { law: "Minimum Wage", jurisdiction: "San Francisco Local", rate: "$18.67/hr", status: "compliant" },
  { law: "Predictive Scheduling", jurisdiction: "Seattle City", rate: "14-day notice", status: "compliant" },
  { law: "Paid Sick Leave", jurisdiction: "Los Angeles County", rate: "48hr accrual", status: "warning" },
  { law: "Overtime Threshold", jurisdiction: "California State", rate: "8hr/day", status: "compliant" },
  { law: "Pay Transparency", jurisdiction: "New York City", rate: "Range req.", status: "compliant" },
  { law: "Fair Workweek", jurisdiction: "Chicago Local", rate: "10-day notice", status: "pending" },
  { law: "Heat Illness Prevention", jurisdiction: "Texas State", rate: "OSHA+", status: "warning" },
  { law: "Ban the Box", jurisdiction: "Portland City", rate: "Active", status: "compliant" },
  { law: "Wage Theft Prevention", jurisdiction: "New York State", rate: "Notice req.", status: "compliant" },
  { law: "Equal Pay Audit", jurisdiction: "Illinois State", rate: "Annual", status: "pending" },
] as const;

const STATUS_COLORS: Record<string, { dot: string; text: string }> = {
  compliant: { dot: "bg-[#4ADE80]", text: "text-[#4ADE80]" },
  warning: { dot: "bg-[#FBBF24]", text: "text-[#FBBF24]" },
  pending: { dot: "bg-white/30", text: "text-white/40" },
};

const VISIBLE_COUNT = 5;

export const JurisdictionRows = memo(function JurisdictionRows() {
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const tickRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let offsetTimer: ReturnType<typeof setInterval> | null = null;
    let tickTimer: ReturnType<typeof setInterval> | null = null;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          offsetTimer = setInterval(() => {
            setOffset((prev) => (prev + 1) % LAWS.length);
          }, 1800);
          tickTimer = setInterval(() => {
            tickRef.current += 1;
            setTick(tickRef.current);
          }, 400);
        } else {
          if (offsetTimer) clearInterval(offsetTimer);
          if (tickTimer) clearInterval(tickTimer);
          offsetTimer = null;
          tickTimer = null;
        }
      },
      { threshold: 0 }
    );
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      if (offsetTimer) clearInterval(offsetTimer);
      if (tickTimer) clearInterval(tickTimer);
    };
  }, []);

  const visibleLaws = Array.from({ length: VISIBLE_COUNT }, (_, i) =>
    LAWS[(offset + i) % LAWS.length]
  );

  const hex = ((tick * 0x1A3F) & 0xFFFF).toString(16).toUpperCase().padStart(4, "0");

  return (
    <div ref={containerRef} className="space-y-0">
      {/* Column headers */}
      <div className="flex items-center px-4 py-2 text-[7px] font-mono uppercase tracking-[0.25em] text-white/20 border-b border-white/5">
        <span className="w-5" />
        <span className="flex-1">Regulation</span>
        <span className="w-40 text-right">Jurisdiction</span>
        <span className="w-24 text-right">Threshold</span>
        <span className="w-16 text-right">Status</span>
      </div>

      <AnimatePresence mode="popLayout">
        {visibleLaws.map((item) => {
          const key = `${item.law}-${item.jurisdiction}`;
          const sc = STATUS_COLORS[item.status];
          return (
            <m.div
              key={key}
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="flex items-center px-4 py-3 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
            >
              <div className={`w-1.5 h-1.5 rounded-full ${sc.dot} mr-3 shrink-0`} />
              <span className="flex-1 text-[11px] font-mono text-white/70 tracking-wide">
                {item.law}
              </span>
              <span className="w-40 text-right text-[9px] font-mono uppercase tracking-[0.15em] text-white/30">
                {item.jurisdiction}
              </span>
              <span className="w-24 text-right text-[9px] font-mono text-white/20">
                {item.rate}
              </span>
              <span className={`w-16 text-right text-[8px] font-mono uppercase tracking-wider ${sc.text}`}>
                {item.status === "compliant" ? "OK" : item.status === "warning" ? "WARN" : "SYNC"}
              </span>
            </m.div>
          );
        })}
      </AnimatePresence>

      {/* Live feed footer */}
      <div className="flex items-center justify-between px-4 pt-3 text-[7px] font-mono uppercase tracking-[0.2em] text-white/15">
        <span>Feed 0x{hex} :: {LAWS.length} regulations tracked</span>
        <span className="animate-pulse">Streaming</span>
      </div>
    </div>
  );
});
