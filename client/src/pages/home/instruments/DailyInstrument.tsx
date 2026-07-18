import { AnimatePresence, motion } from "framer-motion";
import { Lock, Mic, Sparkles } from "lucide-react";
import { ASH, BONE, DISPLAY, LINE_D } from "../theme";
import { InstrumentFrame, useCyclingIndex, useReducedMotion } from "./shared";

export const DAILY_BARS = [3, 5, 2, 6, 4, 1, 4]; // Mon..Sun total — illustrative
export const DAILY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];
// Illustrative category split per day — communicates the AI categorization,
// not just a raw count.
export const DAILY_BEHAVIORAL_PCT = DAILY_BARS.map((v) =>
  Math.round((Math.round(v * 0.6) / v) * 100),
);

// Illustrative waveform shape (not real audio) for the voice-intake demo —
// the magic link's "Dictate" button is a real shipped feature (see
// adminUpdates.ts "ir-magic-link-voice"), this animates what it looks like.
export const VOICE_WAVEFORM = [
  0.3, 0.6, 0.85, 0.5, 0.95, 0.4, 0.7, 0.55, 0.9, 0.35, 0.65, 0.45,
];
// 0-2 are plain status text; phase 3 ("extracted") renders structured
// fields instead of a string — see the voicePhase === 3 branch below.
export const VOICE_STATUS = ["Tap to dictate", "Listening…", "Transcribing…"];
export const VOICE_PHASE_COUNT = 4;

// Actual logged records (illustrative) + their AI analytics — a taste of the
// incident log itself, not just the intake form. Each row: location, type,
// auto-categorized class, severity.
export const RECENT_INCIDENTS = [
  {
    loc: "Atlanta — Store 7",
    type: "Customer escalation",
    sev: "High",
    color: "#ce5a4f",
  },
  {
    loc: "Phoenix — Warehouse",
    type: "Slip / fall",
    sev: "Med",
    color: "#F2C14E",
  },
  { loc: "Dallas — Store 3", type: "Near-miss", sev: "Low", color: "#86efac" },
];

// One report opened with its agentic analysis — the "report itself + its
// data", not just the intake. Illustrative. Index here doubles as the
// "field" a NARRATIVE_TOKENS chunk points at (see below) — same order,
// same meaning, so the highlighted phrase and the resolved fact always match.
export const REPORT_ANALYSIS = [
  { label: "Pattern", value: "3rd escalation · this location · 14 days" },
  { label: "Policy", value: "Workplace Violence Prevention §4" },
  { label: "Action", value: "Manager coaching + security review" },
];

// The raw narrative, broken into plain-text chunks and phrase chunks. Each
// phrase chunk's `field` is an index into REPORT_ANALYSIS — the card sweeps
// a highlight across the phrase that produced each fact, then resolves it
// below, so it *shows* the read instead of just listing conclusions.
export const NARRATIVE_TOKENS: { text: string; field?: number }[] = [
  { text: "Customer got " },
  { text: "aggressive at the register", field: 2 },
  { text: " — " },
  { text: "third time this month", field: 0 },
  { text: ", so this falls under " },
  { text: "workplace violence prevention", field: 1 },
  { text: "." },
];

export function DailyInstrument() {
  const reduce = useReducedMotion();
  const total = DAILY_BARS.reduce((a, b) => a + b, 0);
  const max = Math.max(...DAILY_BARS);
  const voicePhase = useCyclingIndex(VOICE_PHASE_COUNT, 1900, reduce);
  const listening = voicePhase === 1;
  const extractPhase = useCyclingIndex(REPORT_ANALYSIS.length, 2400, reduce);

  return (
    <InstrumentFrame label="Daily Intake" accent="#F2C14E">
      {/* Two-column layout so the card fills its width instead of stacking
          tall. Left = intake + the log; right = the AI analysis + voice.
          Stacks to one column below sm. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      <div className="px-5 pt-3 flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <span
            className="tabular-nums leading-none"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 300,
              fontSize: "3.35rem",
              color: "#F2C14E",
            }}
          >
            {total}
          </span>
          <span className="text-[1rem]" style={{ color: ASH }}>
            /week
          </span>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{
              color: "#86efac",
              backgroundColor: "rgba(134,239,172,0.1)",
            }}
          >
            ▲ 18%
          </span>
        </div>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.2em]"
            style={{ color: "#F2C14E" }}
          >
            Reports
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            via magic link
          </div>
        </div>
      </div>
      <div
        className="px-5 pt-4 pb-2 flex items-end gap-2.5"
        style={{ height: 60 }}
      >
        {DAILY_BARS.map((v, i) => {
          const h = (v / max) * 42;
          const pct = DAILY_BEHAVIORAL_PCT[i];
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1.5">
              <motion.div
                className="w-full rounded-t-sm"
                style={{
                  background: `linear-gradient(to top, rgba(242,193,78,0.9) ${pct}%, rgba(242,193,78,0.38) ${pct}%)`,
                }}
                initial={{ height: 4 }}
                animate={
                  reduce ? { height: h } : { height: [4, h, h * 0.85, h] }
                }
                transition={
                  reduce
                    ? { duration: 0 }
                    : {
                        duration: 2.2,
                        repeat: Infinity,
                        repeatType: "mirror",
                        delay: i * 0.12,
                        ease: "easeInOut",
                      }
                }
              />
              <span className="text-[9px] font-mono" style={{ color: ASH }}>
                {DAILY_LABELS[i]}
              </span>
            </div>
          );
        })}
      </div>
      <div
        className="flex items-center gap-3 px-5 pb-3 pt-1 text-[9px] font-mono uppercase tracking-[0.12em]"
        style={{ color: ASH }}
      >
        <span className="inline-flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-sm"
            style={{ backgroundColor: "rgba(242,193,78,0.9)" }}
          />
          Behavioral
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-sm"
            style={{ backgroundColor: "rgba(242,193,78,0.38)" }}
          />
          Safety
        </span>
      </div>
      {/* The log itself — actual logged records + their auto-categorization
          and severity, so the card shows the output, not just the intake. */}
      <div className="px-5 pt-3 pb-1 border-t" style={{ borderColor: LINE_D }}>
        <div className="flex items-center justify-between mb-2 mt-1">
          <span
            className="text-[9px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Recent incidents
          </span>
          <span
            className="text-[9px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Auto-categorized
          </span>
        </div>
        {RECENT_INCIDENTS.map((r, i) => (
          <motion.div
            key={r.loc}
            initial={reduce ? false : { opacity: 0, x: -6 }}
            whileInView={reduce ? undefined : { opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-20px" }}
            transition={{ delay: i * 0.1, duration: 0.4 }}
            className="flex items-center gap-2.5 py-1.5 border-t first:border-t-0"
            style={{ borderColor: "rgba(245,242,237,0.06)" }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: r.color }}
            />
            <span className="text-[11px] truncate" style={{ color: BONE }}>
              {r.loc}
            </span>
            <span
              className="text-[9px] font-mono truncate hidden sm:inline"
              style={{ color: ASH }}
            >
              {r.type}
            </span>
            <span
              className="ml-auto shrink-0 text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ color: r.color, backgroundColor: `${r.color}1a` }}
            >
              {r.sev}
            </span>
          </motion.div>
        ))}
      </div>
      </div>
      {/* Right column — the AI does the work: analysis + voice intake. */}
      <div
        className="flex flex-col border-t sm:border-t-0 sm:border-l"
        style={{ borderColor: LINE_D }}
      >
      {/* The report opened, with its analysis — pattern detection, policy
          mapping, recommended action. */}
      <div className="px-5 pt-3 pb-3" style={{ borderColor: LINE_D }}>
        <div className="flex items-center gap-2 mb-2.5">
          <span className="text-[10px] font-mono" style={{ color: BONE }}>
            IR-2041
          </span>
          <span
            className="text-[9px] font-mono truncate"
            style={{ color: ASH }}
          >
            Atlanta — Store 7
          </span>
          <span
            className="ml-auto shrink-0 text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{
              color: "#c98a3e",
              backgroundColor: "rgba(201,138,62,0.12)",
              border: "1px solid rgba(201,138,62,0.25)",
            }}
          >
            OSHA recordable
          </span>
        </div>
        <div className="flex items-center gap-1.5 mb-2.5">
          <Sparkles className="w-3 h-3 shrink-0" style={{ color: "#F2C14E" }} />
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Agentic analysis
          </span>
          <span
            className="home-pulse w-1 h-1 rounded-full"
            style={{ backgroundColor: "#F2C14E" }}
          />
        </div>
        {/* The raw report, with the phrase behind the current fact lit up
            as it's "read" — shows the extraction happening instead of
            just listing what it found. */}
        <p
          className="text-[11px] leading-relaxed italic"
          style={{ color: ASH }}
        >
          “
          {NARRATIVE_TOKENS.map((t, i) => {
            const active = t.field === extractPhase;
            return (
              <span
                key={i}
                className="transition-colors duration-500 not-italic"
                style={
                  t.field === undefined
                    ? undefined
                    : {
                        color: active ? "#F2C14E" : ASH,
                        backgroundColor: active
                          ? "rgba(242,193,78,0.12)"
                          : "transparent",
                        borderRadius: 3,
                        padding: active ? "0 3px" : undefined,
                      }
                }
              >
                {t.text}
              </span>
            );
          })}
          ”
        </p>
        <div className="flex items-center gap-2 mt-2.5">
          <span className="text-[10px] shrink-0" style={{ color: "#F2C14E" }}>
            ↳
          </span>
          <AnimatePresence mode="wait">
            <motion.div
              key={extractPhase}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.3 }}
              className="flex items-baseline gap-2.5 min-w-0"
            >
              <span
                className="text-[8px] font-mono uppercase tracking-[0.12em] shrink-0"
                style={{ color: ASH }}
              >
                {REPORT_ANALYSIS[extractPhase].label}
              </span>
              <span
                className="text-[10px] leading-snug truncate"
                style={{ color: BONE }}
              >
                {REPORT_ANALYSIS[extractPhase].value}
              </span>
            </motion.div>
          </AnimatePresence>
        </div>
        <div
          className="flex items-center gap-3 mt-3 pt-2.5 border-t text-[8px] font-mono uppercase tracking-[0.12em]"
          style={{ borderColor: "rgba(245,242,237,0.06)", color: ASH }}
        >
          <span>2 witnesses</span>
          <span style={{ color: LINE_D }}>·</span>
          <span>3 photos</span>
          <span style={{ color: LINE_D }}>·</span>
          <span style={{ color: "#86efac" }}>Routed to manager</span>
        </div>
      </div>
      {/* Voice intake demo — same mockup as the dedicated section on
          /matcha-daily (magic link header, mic, waveform, extracted
          fields), just scaled to fit the hero card. Flush section like the
          one above it — same card, no inner box. */}
      <div
        className="px-5 pt-3 pb-4 border-t transition-colors duration-300"
        style={{ borderColor: listening ? "rgba(242,193,78,0.4)" : LINE_D }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Lock className="w-2.5 h-2.5 shrink-0" style={{ color: ASH }} />
          <span
            className="text-[9px] font-mono truncate"
            style={{ color: ASH }}
          >
            hey-matcha.com/intake/atl7
          </span>
          <span
            className="ml-auto shrink-0 text-[7px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{ border: `1px solid ${LINE_D}`, color: ASH }}
          >
            Public form
          </span>
        </div>

        <div className="flex flex-col items-center text-center py-1">
          <span
            className="text-[8px] font-mono uppercase tracking-widest mb-3"
            style={{ color: ASH }}
          >
            Atlanta — Store 7
          </span>
          <div
            className="relative w-11 h-11 rounded-full flex items-center justify-center mb-2.5 transition-colors duration-300"
            style={{
              backgroundColor: listening
                ? "rgba(242,193,78,0.15)"
                : "rgba(245,242,237,0.05)",
              border: `1px solid ${listening ? "rgba(242,193,78,0.5)" : LINE_D}`,
            }}
          >
            {listening && (
              <span
                className="absolute inset-0 rounded-full animate-ping"
                style={{ backgroundColor: "rgba(242,193,78,0.2)" }}
              />
            )}
            <Mic
              className="w-5 h-5 relative"
              style={{ color: listening ? "#F2C14E" : ASH }}
            />
          </div>
          <div className="flex items-end gap-[2.5px] h-4 mb-2.5">
            {VOICE_WAVEFORM.map((v, i) => (
              <motion.div
                key={i}
                className="w-[2.5px] rounded-full"
                style={{
                  backgroundColor: listening ? "rgba(242,193,78,0.8)" : LINE_D,
                }}
                animate={
                  reduce
                    ? { height: listening ? `${v * 100}%` : "20%" }
                    : {
                        height: listening
                          ? [`${v * 55}%`, `${v * 100}%`, `${v * 55}%`]
                          : "20%",
                      }
                }
                transition={
                  reduce
                    ? { duration: 0 }
                    : {
                        duration: 0.8,
                        repeat: listening ? Infinity : 0,
                        delay: i * 0.05,
                        ease: "easeInOut",
                      }
                }
              />
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.span
              key={voicePhase}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="text-[10px] font-mono"
              style={{
                color:
                  voicePhase === 1
                    ? "#F2C14E"
                    : voicePhase === 3
                      ? "#86efac"
                      : ASH,
              }}
            >
              {voicePhase < 3
                ? VOICE_STATUS[voicePhase]
                : "Report ready for review"}
            </motion.span>
          </AnimatePresence>
        </div>

        <div
          className="grid grid-cols-2 gap-2.5 mt-3 pt-3 border-t transition-opacity duration-500"
          style={{
            borderColor: "rgba(245,242,237,0.06)",
            opacity: voicePhase === 3 ? 1 : 0.25,
          }}
        >
          <div>
            <div
              className="text-[7px] font-mono uppercase tracking-widest mb-0.5"
              style={{ color: ASH }}
            >
              Category
            </div>
            <div className="text-[10px]" style={{ color: BONE }}>
              Customer escalation
            </div>
          </div>
          <div>
            <div
              className="text-[7px] font-mono uppercase tracking-widest mb-0.5"
              style={{ color: ASH }}
            >
              Severity
            </div>
            <div
              className="text-[10px] font-medium"
              style={{ color: "#F2C14E" }}
            >
              Medium
            </div>
          </div>
        </div>
      </div>
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
          Reviewed before it submits
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em] shrink-0 ml-2"
          style={{ color: ASH }}
        >
          Talk or type
        </span>
      </div>
    </InstrumentFrame>
  );
}
