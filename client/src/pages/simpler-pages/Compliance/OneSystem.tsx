import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, Bell, FileText, Library, ListChecks, Scale, Sparkles } from "lucide-react";
import { ASH, BONE, DISPLAY, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER, EYEBROW, SECTION_Y } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";
import { InstrumentFrame, gridCellBorderStyle, useCyclingIndex, useReducedMotion } from "../../home/instruments/shared";
import { COMPLIANCE_COPILOT } from "../../home/instruments/ComplianceInstrument";
import { CAPABILITIES, ONE_SYSTEM_EYEBROW, ONE_SYSTEM_HEADING, ONE_SYSTEM_SUB, type CapabilityItem } from "./data";

const ICONS: Record<CapabilityItem["icon"], typeof Scale> = {
  scale: Scale,
  bell: Bell,
  "file-text": FileText,
  library: Library,
  "badge-check": BadgeCheck,
  "list-checks": ListChecks,
};

/**
 * Replaces the old PillarsGrid (4 alternating rows) + CoverageGrid (6 cards
 * restating 4 of the same 4 pillars) with one section: a dense capability
 * index plus a single small instrument answering the actual objection a
 * self-serve buyer has ("what happens when the law changes") — the hero's
 * ComplianceInstrument already carries the full monitor, so this doesn't
 * repeat it, just the copilot line it cycles.
 */
export function OneSystem() {
  const reduceMotion = useReducedMotion();
  const copilotIndex = useCyclingIndex(COMPLIANCE_COPILOT.length, 3200, reduceMotion);

  return (
    <section className={`${SECTION_Y} border-t`} style={{ borderColor: LINE_D }}>
      <div className={CONTAINER}>
        <Reveal>
          <div className="max-w-2xl mb-12 sm:mb-16">
            <h2 className={EYEBROW} style={{ color: ASH }}>
              {ONE_SYSTEM_EYEBROW}
            </h2>
            <p
              className="mt-4 text-[1.8rem] sm:text-[2.4rem] tracking-[-0.015em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.15, color: BONE }}
            >
              {ONE_SYSTEM_HEADING}
            </p>
            <p className="mt-4 text-[1rem] sm:text-[1.1rem]" style={{ color: ASH, lineHeight: 1.55 }}>
              {ONE_SYSTEM_SUB}
            </p>
          </div>
        </Reveal>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-10 lg:gap-14 items-start">
          <Reveal delayMs={80}>
            <div
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 rounded-xl overflow-hidden border"
              style={{ borderColor: LINE_D }}
            >
              {CAPABILITIES.map((c, i) => {
                const Icon = ICONS[c.icon];
                return (
                  <div
                    key={c.id}
                    className="p-6"
                    style={gridCellBorderStyle(i, CAPABILITIES.length, 3)}
                  >
                    <Icon className="w-5 h-5 mb-4" strokeWidth={1.5} style={{ color: LEAF }} />
                    <h3 className="text-[15px] mb-1.5" style={{ color: BONE, fontWeight: 500 }}>
                      {c.title}
                    </h3>
                    <p className="text-[13px]" style={{ color: ASH, lineHeight: 1.5 }}>
                      {c.caption}
                    </p>
                  </div>
                );
              })}
            </div>
          </Reveal>

          <Reveal delayMs={160}>
            <InstrumentFrame label="Legislation watch" accent="#E2725B">
              <div className="px-5 pt-5 pb-6">
                <Sparkles className="w-4 h-4 mb-3" style={{ color: "#E2725B" }} />
                <AnimatePresence mode="wait">
                  <motion.p
                    key={copilotIndex}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.4 }}
                    className="text-[13px] leading-snug min-h-[3.4em]"
                    style={{ color: BONE }}
                  >
                    {COMPLIANCE_COPILOT[copilotIndex]}
                  </motion.p>
                </AnimatePresence>
              </div>
              <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
                <p className="text-[12px]" style={{ color: ASH, lineHeight: 1.5 }}>
                  When a jurisdiction changes a rule you're subject to, this is what shows up — before an auditor finds it first.
                </p>
              </div>
            </InstrumentFrame>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
