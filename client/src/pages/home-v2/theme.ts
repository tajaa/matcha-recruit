/**
 * Light design system for /home-v2 — cream / matcha green / ink. A parallel
 * token set to pages/home/theme.ts (noir), NOT a variant of it: four other
 * marketing pages (`simpler-pages/*`) import the noir tokens directly, so this
 * file exists to keep this page's palette from leaking into (or depending on)
 * that one. Same inline-`style={{}}` hex convention — consumed directly by
 * SVG presentation attributes in places, so no CSS-variable indirection.
 */

export const CREAM = "#EFEAE0";
export const CREAM_HI = "#F7F4EC";
export const INK = "#14150F";
export const INK_SOFT = "#5E6055";
export const MATCHA = "#3F5C26";
export const MATCHA_MID = "#6E8F4A";
export const MATCHA_LT = "#A3C57D";
export const MATCHA_WASH = "#EDF2E2";
export const LINE = "rgba(20,21,15,0.12)";

export const DISPLAY = "var(--font-display)";
export const SANS = "var(--font-sans)";
