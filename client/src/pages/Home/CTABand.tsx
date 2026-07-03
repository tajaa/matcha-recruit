import { ASH, BONE, DISPLAY, MATCHA, NOIR } from "./theme";

export function CTABand({ onDemoClick }: { onDemoClick: () => void }) {
  return (
    <section className="py-28 sm:py-40">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10 text-center">
        <h2
          className="tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            lineHeight: 0.92,
            fontSize: "clamp(2.75rem, 9vw, 8rem)",
          }}
        >
          Find your{" "}
          <span style={{ color: MATCHA, fontStyle: "italic" }}>
            starting line.
          </span>
        </h2>
        <p
          className="mt-7 mx-auto max-w-lg text-lg"
          style={{ color: ASH, lineHeight: 1.5 }}
        >
          Tell us where you are. We&rsquo;ll tell you which of the four is the
          right place to begin.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
          <button
            onClick={onDemoClick}
            className="inline-flex items-center px-8 rounded-full text-base font-medium transition-transform hover:-translate-y-0.5 cursor-pointer"
            style={{ backgroundColor: MATCHA, color: NOIR, height: 56 }}
          >
            Request a Demo
          </button>
          <a
            href="#index"
            className="inline-flex items-center gap-2 text-base transition-opacity hover:opacity-60"
            style={{ color: BONE }}
          >
            Browse the four
            <span aria-hidden>↑</span>
          </a>
        </div>
      </div>
    </section>
  );
}
