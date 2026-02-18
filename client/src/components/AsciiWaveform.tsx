import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

interface AsciiWaveformProps {
  isRecording: boolean;
  isPlaying: boolean;
  level?: number;
}

const BARS = 48;

function computeHeights(tick: number, isRecording: boolean, isPlaying: boolean, level?: number): number[] {
  const t = tick * 0.16;
  return Array.from({ length: BARS }, (_, i) => {
    const x = (i / BARS) * Math.PI * 4;

    if (isPlaying) {
      const w1 = Math.sin(x + t) * 1.0;
      const w2 = Math.sin(x * 2.5 - t * 1.7) * 0.55;
      const w3 = Math.sin(x * 4.2 + t * 2.5) * 0.28;
      const w4 = Math.sin(x * 7.3 - t * 0.9) * 0.12;
      const w5 = Math.sin(x * 11  + t * 3.2) * 0.06;
      let v = (w1 + w2 + w3 + w4 + w5) / 2.01;
      v = (v + 1) / 2;
      v = Math.pow(v, 0.55); // push peaks up
      return Math.max(0.04, Math.min(1, v));
    }

    if (level !== undefined) {
      const noise = (Math.random() - 0.5) * 0.4;
      const w = Math.sin(x * 2 + t * 4) * 0.5;
      return Math.max(0.04, Math.min(1, ((w + 1) / 2) * level * 0.85 + Math.abs(noise) * level));
    }

    if (isRecording) {
      const noise = Math.random() * 0.55;
      const w = Math.sin(x * 1.8 + t * 3) * 0.45;
      return Math.max(0.04, Math.min(1, (w + 1) / 2 * 0.55 + noise * 0.45));
    }

    return 0;
  });
}

export function AsciiWaveform({ isRecording, isPlaying, level }: AsciiWaveformProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let id: number;
    let last = 0;
    const loop = (ts: number) => {
      if (ts - last > 33) { setTick(t => t + 1); last = ts; }
      id = requestAnimationFrame(loop);
    };
    if (isRecording || isPlaying || level !== undefined) {
      id = requestAnimationFrame(loop);
    } else {
      setTick(0);
    }
    return () => cancelAnimationFrame(id);
  }, [isRecording, isPlaying, level]);

  const active = isRecording || isPlaying || level !== undefined;
  const heights = computeHeights(tick, isRecording, isPlaying, level);

  const barColor = isPlaying
    ? 'bg-emerald-400'
    : isRecording
    ? 'bg-white'
    : 'bg-zinc-700';

  const glowColor = isPlaying
    ? 'rgba(52,211,153,'
    : isRecording
    ? 'rgba(255,255,255,'
    : null;

  return (
    <div className="flex items-end justify-center gap-[2px] h-14 px-1" aria-hidden="true">
      {Array.from({ length: BARS }, (_, i) => {
        const h = active ? heights[i] : 0;
        const glow = glowColor ? `0 0 ${4 + h * 10}px ${glowColor}${0.4 + h * 0.6})` : 'none';
        return (
          <motion.div
            key={i}
            className={`rounded-sm ${barColor}`}
            style={{
              width: 3,
              minHeight: 2,
              boxShadow: glow,
            }}
            animate={{ height: active ? `${Math.max(3, h * 100)}%` : '3px' }}
            transition={{ duration: 0.08, ease: 'easeOut' }}
          />
        );
      })}
    </div>
  );
}
