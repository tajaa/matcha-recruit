import type { CSSProperties } from "react";

/**
 * Skeuomorphic material recipes for the Brokers hero's "Book Risk Console" —
 * a physical-instrument treatment (charcoal chassis, recessed glass, physical
 * knobs) modelled on hardware audio-plugin UIs. Four tiers, each a named
 * recipe here so the whole look is tunable from one place and reusable if the
 * treatment extends past the hero later.
 *
 * Room → Chassis → Module → Glass, darkest to lightest surface, each with a
 * top catch-light + bottom shade + cast shadow so light reads as coming from
 * one consistent source (upper-left, matching the reference).
 *
 * Local dark-room text tokens, not `pages/home/theme.ts`'s BONE/ASH: the rest
 * of this page is noir too now, but the console is meant to read as physical
 * equipment rather than editorial type, so it keeps its own material system
 * rather than pulling in the page's type tokens.
 */
export const ROOM_TEXT = "#EDEFF3";
export const ROOM_MUTED = "rgba(237,239,243,0.5)";

// Accent palette reuses the page's existing risk-band colors (Brokers/data.ts
// BAND_COLOR) plus LEAF — not the reference's blue/orange, so the console
// reads as Matcha hardware, not a rebrand of the screenshot.
export const LEAF = "#A3C57D";
export const AMBER = "#F5B545";
export const CRITICAL = "#FF6B6B";

export const ROOM: CSSProperties = {
  background:
    "radial-gradient(ellipse 90% 70% at 50% -10%, #363B46 0%, #23262E 55%, #1B1E24 100%)",
};

export const CHASSIS: CSSProperties = {
  borderRadius: 26,
  background: "linear-gradient(180deg, #3A3F4A 0%, #2E323B 100%)",
  boxShadow:
    "0 60px 120px -30px rgba(0,0,0,0.75), inset 0 2px 0 rgba(255,255,255,0.10), inset 0 -2px 0 rgba(0,0,0,0.45), 0 0 0 1px rgba(0,0,0,0.55)",
};

export const MODULE: CSSProperties = {
  borderRadius: 14,
  background: "linear-gradient(180deg, #343945 0%, #2B2F39 100%)",
  boxShadow:
    "inset 0 1px 0 rgba(255,255,255,0.07), inset 0 -1px 0 rgba(0,0,0,0.4), 0 8px 18px -8px rgba(0,0,0,0.6)",
};

export const GLASS: CSSProperties = {
  borderRadius: 16,
  backgroundColor: "#0D0F14",
  boxShadow:
    "inset 0 2px 6px rgba(0,0,0,0.9), inset 0 0 0 1px rgba(255,255,255,0.05)",
};

// Inset groove a fader cap rides in.
export const FADER_GROOVE: CSSProperties = {
  borderRadius: 999,
  backgroundColor: "#1A1D23",
  boxShadow: "inset 0 2px 4px rgba(0,0,0,0.7), inset 0 0 0 1px rgba(255,255,255,0.04)",
};

export function knobFace(): CSSProperties {
  return {
    borderRadius: "50%",
    background: "radial-gradient(circle at 32% 26%, #4A5060 0%, #24272F 70%)",
    boxShadow:
      "inset 0 1px 1px rgba(255,255,255,0.18), inset 0 -2px 3px rgba(0,0,0,0.6), 0 3px 6px -2px rgba(0,0,0,0.6)",
  };
}

export function ledGlow(color: string): CSSProperties {
  return {
    backgroundColor: color,
    boxShadow: `0 0 8px ${color}, 0 0 2px ${color}`,
  };
}

export function lcdTile(color: string): CSSProperties {
  return {
    ...GLASS,
    borderRadius: 6,
    color,
    textShadow: `0 0 6px ${color}66`,
  };
}
