import { motion } from "framer-motion";
import { FileText, Lock } from "lucide-react";
import { ASH, BONE, DISPLAY, LINE_D } from "../theme";
import { InstrumentFrame, useReducedMotion } from "./shared";

export const OSHA_300A_TILES = [
  { label: "Total Cases", value: "4", color: BONE },
  { label: "Deaths", value: "0", color: "#ce5a4f" },
  { label: "Days Away", value: "2", sub: "cases", color: "#F2C14E" },
  { label: "Restricted", value: "1", sub: "cases", color: "#c98a3e" },
];
export const OSHA_ROWS = [
  {
    caseNo: "IR-2041-1",
    name: "A. Rivera",
    cls: "Days Away",
    clsColor: "#F2C14E",
    days: "3",
    privacy: false,
  },
  {
    caseNo: "IR-2033-1",
    name: "J. Okafor",
    cls: "Restricted Duty",
    clsColor: "#c98a3e",
    days: "5",
    privacy: false,
  },
  {
    caseNo: "IR-2027-1",
    name: "Privacy Case",
    cls: "Medical Treatment",
    clsColor: ASH,
    days: "—",
    privacy: true,
  },
];
export const OSHA_EXPORTS = ["300 CSV", "300A CSV", "300A PDF", "ITA Export"];

export function OshaLogInstrument() {
  const reduce = useReducedMotion();
  return (
    <InstrumentFrame label="OSHA 300 Log" accent="#F2C14E">
      {/* Two-column: left = headline + 300A roll-up + exports, right = the
          Form 300 log itself. Stacks to one column below sm. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      {/* Recordables headline — the payoff of flipping "OSHA recordable" on an
          incident: it lands here, per establishment, per year. */}
      <div className="px-5 pt-4 flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <span
            className="tabular-nums leading-none"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 300,
              fontSize: "3rem",
              color: "#F2C14E",
            }}
          >
            4
          </span>
          <span className="text-[0.85rem]" style={{ color: ASH }}>
            recordable YTD
          </span>
        </div>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.18em]"
            style={{ color: BONE }}
          >
            Atlanta — Store 7
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Establishment · 2026
          </div>
        </div>
      </div>

      {/* 300A summary tiles — the annual roll-up, auto-computed from the log. */}
      <div className="px-5 pt-4 grid grid-cols-2 gap-2">
        {OSHA_300A_TILES.map((t) => (
          <div
            key={t.label}
            className="rounded-lg border px-2.5 py-2"
            style={{
              borderColor: LINE_D,
              backgroundColor: "rgba(245,242,237,0.02)",
            }}
          >
            <div
              className="tabular-nums leading-none mb-1"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                fontSize: "1.4rem",
                color: t.color,
              }}
            >
              {t.value}
            </div>
            <div
              className="text-[7px] font-mono uppercase tracking-[0.1em]"
              style={{ color: ASH }}
            >
              {t.label}
              {t.sub ? ` · ${t.sub}` : ""}
            </div>
          </div>
        ))}
      </div>

      {/* One-tap exports — the shipped file set (300 CSV / 300A CSV / 300A PDF
          / ITA), each behind a reviewer attestation. */}
      <div className="px-5 pt-4 pb-4 flex flex-wrap gap-1.5">
        {OSHA_EXPORTS.map((e) => (
          <span
            key={e}
            className="inline-flex items-center gap-1.5 text-[8px] font-mono uppercase tracking-wider px-2 py-1 rounded"
            style={{ border: `1px solid ${LINE_D}`, color: ASH }}
          >
            <FileText className="w-2.5 h-2.5" style={{ color: "#F2C14E" }} />
            {e}
          </span>
        ))}
      </div>
      </div>
      {/* Right column — the Form 300 log itself. */}
      <div
        className="flex flex-col border-t sm:border-t-0 sm:border-l"
        style={{ borderColor: LINE_D }}
      >
      {/* Form 300 rows — real columns: Case # / Employee / Classification /
          Days. The privacy row prints the mask, never the name. */}
      <div className="px-5 pt-4 pb-4">
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Form 300 · Log of injuries &amp; illnesses
          </span>
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: "#86efac" }}
          >
            ● Recordable
          </span>
        </div>
        <div
          className="grid items-center gap-2 pb-1.5 mb-1 border-b text-[7px] font-mono uppercase tracking-[0.1em]"
          style={{
            gridTemplateColumns: "auto 1fr auto auto",
            borderColor: LINE_D,
            color: ASH,
          }}
        >
          <span>Case #</span>
          <span>Employee</span>
          <span>Classification</span>
          <span className="text-right">Days</span>
        </div>
        {OSHA_ROWS.map((r, i) => (
          <motion.div
            key={r.caseNo}
            initial={reduce ? false : { opacity: 0, x: -6 }}
            whileInView={reduce ? undefined : { opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-20px" }}
            transition={{ delay: i * 0.1, duration: 0.4 }}
            className="grid items-center gap-2 py-1.5 border-t first:border-t-0"
            style={{
              gridTemplateColumns: "auto 1fr auto auto",
              borderColor: "rgba(245,242,237,0.06)",
            }}
          >
            <span
              className="text-[9px] font-mono tabular-nums"
              style={{ color: ASH }}
            >
              {r.caseNo}
            </span>
            <span className="flex items-center gap-1.5 min-w-0">
              {r.privacy && (
                <Lock className="w-2.5 h-2.5 shrink-0" style={{ color: ASH }} />
              )}
              <span
                className="text-[10px] truncate"
                style={{
                  color: r.privacy ? ASH : BONE,
                  fontStyle: r.privacy ? "italic" : "normal",
                }}
              >
                {r.name}
              </span>
            </span>
            <span
              className="shrink-0 text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ color: r.clsColor, backgroundColor: `${r.clsColor}1a` }}
            >
              {r.cls}
            </span>
            <span
              className="text-[10px] tabular-nums text-right"
              style={{ color: BONE }}
            >
              {r.days}
            </span>
          </motion.div>
        ))}
      </div>

      </div>
      </div>

      <div
        className="flex items-center justify-between px-5 pb-4 pt-3 border-t"
        style={{ borderColor: LINE_D }}
      >
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: "#86efac" }}
        >
          300A ready for Feb 1 posting
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em] shrink-0 ml-2"
          style={{ color: ASH }}
        >
          Per establishment
        </span>
      </div>
    </InstrumentFrame>
  );
}
