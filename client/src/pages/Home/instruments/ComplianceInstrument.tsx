import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react";
import { ASH, BONE, DISPLAY, LINE_D } from "../theme";
import { InstrumentFrame, gridCellBorderStyle, useCyclingIndex, useReducedMotion } from "./shared";

export const COMPLIANCE_CHIPS = [
  { code: "CA", resolved: true },
  { code: "NY", resolved: true },
  { code: "FED", resolved: false },
  { code: "WA", resolved: false },
  { code: "IL", resolved: false },
  { code: "TX", resolved: false },
];

export type FindingStatus = "flagged" | "fixing" | "fixed";

export const COMPLIANCE_FINDINGS: { state: string; text: string }[] = [
  { state: "CA", text: "Meal period waivers missing for 12 employees" },
  { state: "NY", text: "Paid sick leave accrual rate below statute" },
  { state: "FED", text: "FLSA overtime threshold update not applied" },
  { state: "WA", text: "Predictive scheduling notice window expired" },
  { state: "IL", text: "BIPA biometric consent forms unsigned" },
  { state: "TX", text: "Anti-retaliation posters out of date" },
];

// AI action layer — grounded in the real product's legislation-watch worker
// + alerts/action-plans (root CLAUDE.md). Cycles like Platform's ER Copilot.
export const COMPLIANCE_COPILOT = [
  "Legislation watch: new CA pay-transparency rule effective Jul 1.",
  "Action plan: file WA predictive-scheduling notice by Mar 14.",
  "Auto-drafted: updated anti-retaliation poster ready to post.",
];

// Coverage across compliance areas, not just jurisdictions — the breadth grid,
// mirroring Platform's domain grid. Illustrative.
export const COMPLIANCE_CATEGORIES = [
  { label: "Wage & Hour", status: "Gap", color: "#E2725B" },
  { label: "Leave & Sick", status: "Clear", color: "#86efac" },
  { label: "Safety / OSHA", status: "Gap", color: "#E2725B" },
  { label: "Posting", status: "Scan", color: "#d9b65f" },
  { label: "Classification", status: "Clear", color: "#86efac" },
  { label: "Pay Equity", status: "Clear", color: "#86efac" },
] as const;

export const FINDING_ICON = {
  flagged: AlertTriangle,
  fixing: Loader2,
  fixed: CheckCircle2,
} as const;
export const FINDING_COLOR = {
  flagged: "#E2725B",
  fixing: "#d9b65f",
  fixed: "#86efac",
} as const;

// Mirrors the real flag → fixing → fixed cascade from the actual /compliance
// page's live engine, staggered per row and looping, instead of a static list.
export function useFindingsCascade(count: number, reduce: boolean) {
  const [statuses, setStatuses] = useState<FindingStatus[]>(() =>
    Array(count).fill("flagged"),
  );

  useEffect(() => {
    if (reduce) {
      setStatuses(
        Array.from({ length: count }, (_, i) => (i < 2 ? "fixed" : "flagged")),
      );
      return;
    }
    const STEP = 1600;
    const ROW_STAGGER = 900;
    const CYCLE = STEP * 2 + count * ROW_STAGGER + 2000;
    let timers: number[] = [];

    const runCycle = () => {
      setStatuses(Array(count).fill("flagged"));
      for (let i = 0; i < count; i++) {
        timers.push(
          window.setTimeout(
            () => {
              setStatuses((s) => s.map((v, j) => (j === i ? "fixing" : v)));
            },
            STEP + i * ROW_STAGGER,
          ),
        );
        timers.push(
          window.setTimeout(
            () => {
              setStatuses((s) => s.map((v, j) => (j === i ? "fixed" : v)));
            },
            STEP * 2 + i * ROW_STAGGER,
          ),
        );
      }
    };

    runCycle();
    const loop = window.setInterval(runCycle, CYCLE);
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      window.clearInterval(loop);
      timers = [];
    };
  }, [count, reduce]);

  return statuses;
}

export function ComplianceInstrument() {
  const TARGET = 60;
  const reduce = useReducedMotion();
  const [score, setScore] = useState(reduce ? TARGET : 0);
  const copilotIndex = useCyclingIndex(COMPLIANCE_COPILOT.length, 3200, reduce);
  const findingStatuses = useFindingsCascade(
    COMPLIANCE_FINDINGS.length,
    reduce,
  );

  useEffect(() => {
    if (reduce) return;
    const DUR = 1200;
    let raf = 0;
    let start = 0;
    const loop = (now: number) => {
      if (!start) start = now;
      const e = now - start;
      const intro = Math.min(1, e / DUR);
      const eased = 1 - Math.pow(1 - intro, 3);
      setScore(Math.round(eased * TARGET));
      if (intro < 1) raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [reduce]);

  const resolvedCount = COMPLIANCE_CHIPS.filter((c) => c.resolved).length;

  return (
    <InstrumentFrame label="Compliance Monitor" accent="#E2725B">
      {/* Two-column: left = score + jurisdictions + the AI copilot, right =
          the live findings cascade. Coverage grid spans full width below.
          Stacks to one column below sm. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      <div className="px-5 pt-4 flex items-end justify-between">
        <span
          className="tabular-nums leading-none"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            fontSize: "3.5rem",
            color: "#E2725B",
          }}
        >
          {score}
          <span className="ml-1 align-top text-[0.9rem]" style={{ color: ASH }}>
            /100
          </span>
        </span>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.2em]"
            style={{ color: "#E2725B" }}
          >
            {resolvedCount}/{COMPLIANCE_CHIPS.length} resolved
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Next: WA in 9d
          </div>
        </div>
      </div>
      <div className="px-5 pt-5 flex flex-wrap gap-2">
        {COMPLIANCE_CHIPS.map((c) => (
          <span
            key={c.code}
            className="px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider"
            style={{
              border: `1px solid ${c.resolved ? "rgba(134,239,172,0.35)" : "rgba(226,114,91,0.35)"}`,
              color: c.resolved ? "#86efac" : "#E2725B",
              backgroundColor: c.resolved
                ? "rgba(134,239,172,0.08)"
                : "rgba(226,114,91,0.08)",
            }}
          >
            {c.code} {c.resolved ? "✓" : "!"}
          </span>
        ))}
      </div>
      <div className="px-5 pt-4 pb-4">
        <div
          className="rounded-lg px-3.5 py-2.5 flex items-start gap-2.5"
          style={{
            border: `1px solid ${LINE_D}`,
            backgroundColor: "rgba(245,242,237,0.03)",
          }}
        >
          <Sparkles
            className="w-3.5 h-3.5 mt-0.5 shrink-0"
            style={{ color: "#E2725B" }}
          />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span
                className="text-[8px] font-mono uppercase tracking-[0.16em]"
                style={{ color: ASH }}
              >
                Compliance Copilot
              </span>
              <span
                className="home-pulse w-1 h-1 rounded-full"
                style={{ backgroundColor: "#E2725B" }}
              />
            </div>
            <AnimatePresence mode="wait">
              <motion.p
                key={copilotIndex}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.4 }}
                className="text-[11px] leading-snug"
                style={{ color: BONE }}
              >
                {COMPLIANCE_COPILOT[copilotIndex]}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
      </div>
      </div>
      {/* Right column — the flag → fixing → fixed cascade. */}
      <div
        className="flex flex-col border-t sm:border-t-0 sm:border-l"
        style={{ borderColor: LINE_D }}
      >
      <div className="px-5 pb-3 pt-3">
        {COMPLIANCE_FINDINGS.map((f, i) => {
          const status = findingStatuses[i];
          const Icon = FINDING_ICON[status];
          return (
            <div key={f.state} className="flex items-center gap-2.5 py-1.5">
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded shrink-0"
                style={{ border: `1px solid ${LINE_D}`, color: ASH }}
              >
                {f.state}
              </span>
              <span
                className="text-[11px] flex-1 truncate transition-colors duration-300"
                style={{
                  color: status === "fixed" ? ASH : BONE,
                  textDecoration:
                    status === "fixed"
                      ? "line-through rgba(245,242,237,0.4)"
                      : "none",
                }}
              >
                {f.text}
              </span>
              <Icon
                className={`w-3.5 h-3.5 shrink-0 ${status === "fixing" ? "animate-spin" : ""}`}
                style={{ color: FINDING_COLOR[status] }}
              />
            </div>
          );
        })}
      </div>
      </div>
      </div>
      {/* Breadth — coverage across every compliance area, not just the open
          findings. Mirrors Platform's domain grid. Spans full width below
          the two columns. */}
      <div
        className="px-5 pt-4 pb-4 border-t"
        style={{ borderColor: LINE_D }}
      >
        <div className="flex items-center justify-between mb-2.5">
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Coverage by area
          </span>
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            247 reqs
          </span>
        </div>
        <div
          className="grid grid-cols-3 rounded-lg overflow-hidden border"
          style={{
            borderColor: LINE_D,
            backgroundColor: "rgba(245,242,237,0.02)",
          }}
        >
          {COMPLIANCE_CATEGORIES.map((c, i) => (
            <div
              key={c.label}
              className="px-2.5 py-2"
              style={gridCellBorderStyle(i, COMPLIANCE_CATEGORIES.length)}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: c.color }}
                />
                <span
                  className="text-[8px] font-mono uppercase tracking-[0.1em] truncate"
                  style={{ color: ASH }}
                >
                  {c.label}
                </span>
              </div>
              <span
                className="text-[11px] font-mono"
                style={{ color: c.color }}
              >
                {c.status}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div
        className="flex items-center justify-between px-5 pb-4 pt-3 border-t"
        style={{ borderColor: LINE_D }}
      >
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ASH }}
        >
          247 requirements scanned
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ASH }}
        >
          Updated just now
        </span>
      </div>
    </InstrumentFrame>
  );
}
