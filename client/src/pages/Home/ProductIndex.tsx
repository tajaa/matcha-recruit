import { useState } from "react";
import { Link } from "react-router-dom";
import { PRODUCTS } from "./data";
import { ASH, BONE, DISPLAY, LINE_D, NOIR } from "./theme";
import { Reveal } from "./PageChrome";

export function ProductIndex() {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <section id="index" className="scroll-mt-16 py-20 sm:py-28">
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 lg:px-16 xl:px-24">
        <Reveal>
          <div className="flex items-baseline justify-between mb-2">
            <h2
              className="text-[11px] tracking-[0.3em] font-mono uppercase"
              style={{ color: ASH }}
            >
              Four ways in
            </h2>
            <span
              className="text-[11px] tracking-[0.3em] font-mono uppercase"
              style={{ color: ASH }}
            >
              Index
            </span>
          </div>
        </Reveal>

        <div className="border-t" style={{ borderColor: LINE_D }}>
          {PRODUCTS.map((p, i) => {
            const active = hovered === i;
            return (
              <Reveal key={p.name} delayMs={Math.min(i * 70, 210)}>
              <Link
                to={p.to}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                className="group relative grid grid-cols-[auto_1fr] sm:grid-cols-[auto_1fr_auto] items-center gap-x-5 sm:gap-x-10 border-b px-2 sm:px-6 py-7 sm:py-10 transition-colors duration-300"
                style={{
                  borderColor: LINE_D,
                  backgroundColor: active ? p.accent : "transparent",
                  color: active ? NOIR : BONE,
                }}
              >
                <span
                  className="font-mono text-sm sm:text-base self-start pt-2 sm:pt-4 transition-colors duration-300"
                  style={{ color: active ? NOIR : p.accent }}
                >
                  {p.n}
                </span>

                <div className="min-w-0">
                  <h3
                    className="tracking-[-0.02em] transition-transform duration-300 group-hover:translate-x-2"
                    style={{
                      fontFamily: DISPLAY,
                      fontWeight: 400,
                      lineHeight: 0.95,
                      fontSize: "clamp(2.25rem, 7vw, 5.5rem)",
                    }}
                  >
                    {p.name}
                  </h3>
                  <p
                    className="mt-3 max-w-2xl text-[15px] sm:text-lg transition-colors duration-300"
                    style={{
                      color: active ? "rgba(14,14,12,0.72)" : ASH,
                      lineHeight: 1.5,
                    }}
                  >
                    {p.blurb}
                  </p>
                </div>

                <span
                  className="hidden sm:inline-flex items-center gap-2 font-mono text-sm uppercase tracking-[0.2em] justify-self-end transition-all duration-300"
                  style={{
                    color: active ? NOIR : BONE,
                    opacity: active ? 1 : 0.55,
                  }}
                >
                  Enter
                  <span
                    className="transition-transform duration-300 group-hover:translate-x-1.5"
                    aria-hidden
                  >
                    →
                  </span>
                </span>
              </Link>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
