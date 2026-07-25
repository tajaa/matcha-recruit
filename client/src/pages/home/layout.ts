/**
 * Layout recipes for the noir marketing surface (pages/home/* + StartQualify).
 *
 * theme.ts owns colour; this file owns rhythm — the container, the vertical
 * scale, and the eyebrow. Before it existed each section improvised its own
 * (`py-20 sm:py-28` / `py-24 sm:py-36` / `py-28 sm:py-40`, three different
 * eyebrow sizes, and four container widths on one continuous page), so nothing
 * lined up down the left edge as you scrolled.
 *
 * EVERY VALUE HERE MUST BE A COMPLETE CLASS-STRING LITERAL. Tailwind v4 scans
 * raw source text, so an interpolated class (`px-${n}`) compiles to no CSS at
 * all and fails silently at runtime.
 */

/**
 * The one container. Matches MarketingNav + MarketingFooter exactly
 * (`max-w-[1440px] … px-6 sm:px-10`), which is already the site-wide standard —
 * 25 other marketing surfaces use it. The homepage was the deviant, and the
 * ~24px offset between the nav wordmark and the h1 was the visible symptom.
 *
 * At >=1440px this yields a 1360px content box, which is why the carousel's old
 * `max-w-[1360px]` wrapper is gone: the container already produces that width.
 */
export const CONTAINER = "max-w-[1440px] mx-auto w-full px-6 sm:px-10";

/** Body sections. The `md:` step is the band the homepage used to skip entirely. */
export const SECTION_Y = "py-20 sm:py-28 md:py-32";

/** The closing CTA only — a page's last section earns more air than its middle. */
export const SECTION_Y_LG = "py-28 sm:py-36 md:py-44";

/**
 * Eyebrow / folio label.
 *
 * 11px @ 0.22em, not the old 10.5px @ 0.28-0.3em: those were tuned against the
 * UA monospace fallback. Space Mono has a ~0.6em advance and a low x-height, so
 * 0.28em pushes letter gaps past 45% of glyph width (words stop cohering) and
 * 10.5px sub-pixel-rounds its thin 400 stems to fuzz against ash-on-noir.
 */
export const EYEBROW =
  "text-[11px] font-mk-mono uppercase tracking-[0.22em]";

/**
 * Right-aligned eyebrows. `letter-spacing` adds trailing space AFTER the last
 * glyph, so a right-aligned label hangs ~2.4px short of the rule above it. The
 * negative margin pulls the optical edge back onto the grid.
 */
export const EYEBROW_END = `${EYEBROW} mr-[-0.22em]`;
