import { DISPLAY, MATCHA, NOIR } from "./theme";

export function Manifesto() {
  return (
    <section
      style={{ backgroundColor: MATCHA, color: NOIR }}
      className="py-24 sm:py-36"
    >
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10 lg:px-16 xl:px-24">
        <span className="text-[11px] tracking-[0.3em] font-mono uppercase">
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            lineHeight: 1.04,
            fontSize: "clamp(2rem, 5.5vw, 4.75rem)",
          }}
        >
          We don&rsquo;t ship software and walk away. We take responsibility for
          the hardest, most <span style={{ fontStyle: "italic" }}>human</span>{" "}
          part of your company.
        </p>
      </div>
    </section>
  );
}
