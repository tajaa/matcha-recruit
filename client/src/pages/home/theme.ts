/**
 * Colour tokens for the NOIR marketing surface — pages/home/* plus
 * pages/landing/StartQualify.tsx (the /start funnel, which must stay visually
 * continuous with the hero it's launched from).
 *
 * The bone/light marketing pages (simpler-pages/*, MarketingFooter) are a
 * different surface and own their colour through the `--color-ivory-*` tokens
 * in index.css. Don't cross the streams.
 *
 * Layout rhythm (container, section padding, eyebrow) lives in ./layout.ts.
 *
 * Values are consumed as inline `style={{}}` rather than Tailwind utilities, so
 * they stay plain hex strings — two SVG *presentation attributes* read them
 * directly (PlatformInstrument.tsx `stroke={LINE_D}` / `stroke={BONE}`), and
 * `stroke="var(--x)"` as an attribute does not resolve. If these ever move into
 * the `@theme` block, convert those two to `style={{ stroke: … }}` first.
 */
export const NOIR = "#0E0E0C";
export const BONE = "#F5F2ED";
export const ASH = "#8F8B80";
export const LEAF = "#A3C57D"; // matcha-green accent (dots, focus, primary fill)
export const LEAF_HI = "#BCD897"; // lighter leaf — gradient top-stop on the mark
export const AMBER = "#D97706"; // warm accent (headline "risk", caret, errors)
export const LINE_D = "rgba(245,242,237,0.14)";
export const SURFACE = "rgba(245,242,237,0.045)"; // raised panel on noir
export const DISPLAY = "var(--font-display)"; // Fraunces

/*
 * REMOVED: `MATCHA`. It was an alias for BONE (#F5F2ED), not the green its name
 * implied, and every call site was written as though it were an accent —
 * `<span style={{ color: MATCHA }}>` on bone-on-noir text produced no emphasis
 * at all. It cost the hero headline half of its two-colour pairing and the
 * closing CTA its entire accent. Use BONE where you want bone, LEAF where you
 * want green.
 */
