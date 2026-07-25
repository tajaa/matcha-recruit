import { ROOM, ROOM_MUTED, ROOM_TEXT, LEAF } from "./console/materials";
import { RiskConsole } from "./console/RiskConsole";

/**
 * Dark studio band, headline above a wide skeuomorphic console — replaces the
 * flat BookRiskCurveCard list with a "Book Risk Console" instrument (charcoal
 * chassis, recessed glass, physical knobs/faders; see console/materials.ts).
 * The rest of the page is now noir too (pages/home/* tokens), so this band's
 * ROOM gradient is a tonal step within one dark surface, not a cut against an
 * ivory page — it stays its own material rather than switching to BONE/ASH
 * because it's meant to read as equipment, not editorial type.
 *
 * pt clears the one fixed bar this page mounts: MarketingNav (64px). The
 * ComplianceTicker that used to add another 40px is gone from this page.
 */
export function Hero({ onBookClick }: { onBookClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={ROOM}>
      <div className="relative z-10 max-w-[1440px] mx-auto px-6 sm:px-10 pt-[88px] sm:pt-[96px] pb-16 sm:pb-20">
        <div className="max-w-2xl">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-8"
            style={{ backgroundColor: "rgba(237,239,243,0.06)", color: ROOM_MUTED }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: LEAF }} />
            <span className="text-[11px] uppercase tracking-wider font-medium">
              For P&amp;C brokers
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight"
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 400,
              color: ROOM_TEXT,
              fontSize: "clamp(2.75rem, 6vw, 5.25rem)",
            }}
          >
            The intelligence layer for your whole book.
          </h1>
          <p
            className="mt-6 max-w-lg"
            style={{ color: ROOM_MUTED, fontSize: "clamp(1rem, 1.15vw, 1.125rem)", lineHeight: 1.55 }}
          >
            Your clients run a live safety intake system. You get back what no
            carrier portal gives you — real-time TRIR, DART, and loss trends,
            plus risk alerts and suggested actions, across every account you
            manage.
          </p>
          <div className="mt-10 flex items-center gap-4 flex-wrap">
            <button
              onClick={onBookClick}
              className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: ROOM_TEXT, color: "#1B1E24" }}
            >
              Book a Walkthrough
            </button>
          </div>
        </div>

        <div className="mt-14 sm:mt-16">
          <RiskConsole />
        </div>
      </div>
    </section>
  );
}
