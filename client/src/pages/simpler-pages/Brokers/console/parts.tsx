import type { CSSProperties, ReactNode } from "react";
import { FADER_GROOVE, GLASS, MODULE, ROOM_MUTED, ROOM_TEXT, knobFace, lcdTile, ledGlow } from "./materials";

// Dumb, presentational hardware parts. All sizing goes through `style` —
// Tailwind v4 cannot compile interpolated classes (e.g. `w-[${n}px]`), so
// every dimension here is inline.

const TICK_COUNT = 11;
const KNOB_MIN_DEG = -130;
const KNOB_MAX_DEG = 130;

/**
 * A physical rotary knob. `value` is 0..1; the indicator sweeps
 * KNOB_MIN_DEG..KNOB_MAX_DEG and rim ticks mark the same range at rest.
 */
export function Knob({
  value,
  accent,
  size = 56,
}: {
  value: number;
  accent: string;
  size?: number;
}) {
  const angle = KNOB_MIN_DEG + Math.max(0, Math.min(1, value)) * (KNOB_MAX_DEG - KNOB_MIN_DEG);
  const radius = size / 2;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      {Array.from({ length: TICK_COUNT }, (_, i) => {
        const t = i / (TICK_COUNT - 1);
        const tickDeg = KNOB_MIN_DEG + t * (KNOB_MAX_DEG - KNOB_MIN_DEG);
        const rad = (tickDeg * Math.PI) / 180;
        const r = radius + 5;
        const x = radius + r * Math.sin(rad);
        const y = radius - r * Math.cos(rad);
        return (
          <span
            key={i}
            className="absolute rounded-full"
            style={{
              width: 2,
              height: 2,
              left: x - 1,
              top: y - 1,
              backgroundColor: "rgba(237,239,243,0.22)",
            }}
          />
        );
      })}
      <div className="absolute inset-0" style={knobFace()}>
        <div
          className="absolute left-1/2"
          style={{
            top: "16%",
            width: 2,
            height: "32%",
            backgroundColor: accent,
            boxShadow: `0 0 4px ${accent}`,
            transformOrigin: `1px ${size * 0.34}px`,
            transform: `translateX(-1px) rotate(${angle}deg)`,
            borderRadius: 2,
          }}
        />
      </div>
    </div>
  );
}

export function Led({
  color,
  size = 6,
  pulse = false,
}: {
  color: string;
  size?: number;
  pulse?: boolean;
}) {
  return (
    <span
      className={`inline-block rounded-full ${pulse ? "console-led-pulse" : ""}`}
      style={{ width: size, height: size, ...ledGlow(color) }}
    />
  );
}

export function Lcd({
  label,
  value,
  unit,
  accent,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  accent: string;
}) {
  return (
    <div className="px-2.5 py-2" style={lcdTile(accent)}>
      <div
        className="text-[8px] font-mono uppercase tracking-[0.14em] mb-0.5"
        style={{ color: ROOM_MUTED }}
      >
        {label}
      </div>
      <div className="flex items-baseline gap-1 tabular-nums" style={{ fontSize: 15, fontWeight: 600 }}>
        {value}
        {unit && (
          <span className="text-[10px]" style={{ color: `${accent}99` }}>
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}

export function Fader({
  value,
  accent,
  height = 130,
}: {
  value: number;
  accent: string;
  height?: number;
}) {
  const capTravel = height - 18;
  const capY = (1 - Math.max(0, Math.min(1, value))) * capTravel;
  return (
    <div className="relative w-3 mx-auto" style={{ height, ...FADER_GROOVE }}>
      <div
        className="absolute left-1/2 rounded-full"
        style={{
          width: 22,
          height: 11,
          top: capY,
          transform: "translateX(-50%)",
          background: "linear-gradient(180deg, #565C6A 0%, #363B45 100%)",
          boxShadow: "0 2px 5px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.2)",
          borderRadius: 3,
        }}
      >
        <div
          className="absolute left-1/2 top-1/2 rounded-full"
          style={{
            width: 14,
            height: 1.5,
            transform: "translate(-50%,-50%)",
            backgroundColor: accent,
            boxShadow: `0 0 3px ${accent}`,
          }}
        />
      </div>
    </div>
  );
}

export function ModulePanel({
  label,
  accent,
  children,
  style,
}: {
  label: string;
  accent: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div className="flex-1 min-w-0 px-3.5 pt-3 pb-3.5" style={{ ...MODULE, ...style }}>
      <div className="flex items-center justify-between mb-2.5">
        <span
          className="text-[10px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ROOM_TEXT }}
        >
          {label}
        </span>
        <Led color={accent} pulse />
      </div>
      {children}
    </div>
  );
}

// Glowing "tube" tile — Loss Control's illustrative saturation stage, echoing
// the reference's TUBE tile without copying its literal artwork.
export function TubeTile({ accent }: { accent: string }) {
  return (
    <div
      className="rounded-md h-9 flex items-center justify-center"
      style={{ ...GLASS, background: `linear-gradient(180deg, ${accent}33, #0D0F14 70%)` }}
    >
      <div
        className="rounded-full"
        style={{ width: 8, height: 18, backgroundColor: accent, boxShadow: `0 0 10px ${accent}` }}
      />
    </div>
  );
}

// Waveform tile — Outreach's illustrative activity strip.
export function WaveTile({ accent }: { accent: string }) {
  const bars = [3, 7, 5, 10, 6, 13, 8, 11, 4, 9, 6];
  return (
    <div className="rounded-md h-9 flex items-center justify-center gap-[3px] px-2" style={GLASS}>
      {bars.map((h, i) => (
        <span
          key={i}
          className="rounded-full"
          style={{ width: 2, height: h, backgroundColor: accent, opacity: 0.55 + (i % 3) * 0.15 }}
        />
      ))}
    </div>
  );
}
