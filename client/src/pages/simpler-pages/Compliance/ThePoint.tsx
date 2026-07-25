import { ASH, BONE, DISPLAY, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER, EYEBROW, SECTION_Y } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";

// The best writing on the old page — kept verbatim, re-tokened onto noir.
export function ThePoint() {
  return (
    <section className={`${SECTION_Y} border-t`} style={{ borderColor: LINE_D }}>
      <Reveal className={CONTAINER}>
        <span className={EYEBROW} style={{ color: ASH }}>
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            color: BONE,
            lineHeight: 1.1,
            fontSize: "clamp(2rem, 5vw, 4.25rem)",
          }}
        >
          We don't ship a checklist and disappear. We stay responsible for
          keeping it{" "}
          <span style={{ color: LEAF, fontStyle: "italic" }}>current</span> —
          so you're never the one who finds out the hard way.
        </p>
      </Reveal>
    </section>
  );
}
