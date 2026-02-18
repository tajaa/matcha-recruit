import { useEffect, useState } from 'react';

interface AsciiWaveformProps {
  isRecording: boolean;
  isPlaying: boolean;
  level?: number;
}

const COLS = 32;
// Block characters for height: 0 to 7
const CHARS = [' ', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

export function AsciiWaveform({ isRecording, isPlaying, level }: AsciiWaveformProps) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    let animationFrameId: number;

    const animate = () => {
      setFrame((f) => f + 1);
      animationFrameId = requestAnimationFrame(animate);
    };

    if (isRecording || isPlaying || level !== undefined) {
      animate();
    } else {
      // Gently pulse idle state? Or just reset.
      // Let's reset for now to show "silence" clearly.
      setFrame(0);
    }

    return () => cancelAnimationFrame(animationFrameId);
  }, [isRecording, isPlaying, level]);

  const renderWave = () => {
    // If idle, render flat line
    if (!isRecording && !isPlaying && level === undefined) {
      return Array(COLS).fill(' ').join('');
    }

    let output = '';
    const time = frame * 0.2; // Speed

    for (let i = 0; i < COLS; i++) {
      // Center the wave
      const x = i - COLS / 2;
      
      let value = 0;
      
      if (level !== undefined) {
        // Real-time volume visualization
        // Use a fast sine wave modulated by volume level
        // Randomize phase slightly to look organic
        const noise = Math.random() * 0.2;
        const wave = (Math.sin(x * 0.8 + time * 3) + 1) / 2;
        value = (wave * 0.8 + noise) * level * 1.5; // Boost gain slightly
      } else if (isPlaying) {
        // AI Speaking: Smooth, symmetric, harmonic
        // Combination of sine waves
        const wave1 = Math.sin(x * 0.2 + time);
        const wave2 = Math.sin(x * 0.4 - time * 1.5) * 0.5;
        // Envelope to taper edges
        const envelope = 1 - Math.abs(x) / (COLS / 2);
        
        value = (wave1 + wave2) * envelope;
        // Normalize roughly to 0-1 range (sine is -1.5 to 1.5)
        value = (value + 1.5) / 3;
      } else {
        // User Speaking: Random, jittery, voice-like
        // Noise + fast sine
        const noise = Math.random() * 0.5;
        const wave = Math.sin(x * 0.8 + time * 2) * 0.5;
        const envelope = 1 - Math.abs(x) / (COLS / 2);
        
        value = (wave + noise) * envelope;
        // Normalize
        value = (value + 1) / 2;
      }

      // Clamp and map
      value = Math.max(0, Math.min(1, value));
      const charIndex = Math.floor(value * (CHARS.length - 1));
      output += CHARS[charIndex];
    }
    
    return output;
  };

  return (
    <div 
      className={`font-mono text-lg overflow-hidden whitespace-pre tracking-[0.1em] leading-none select-none text-center transition-colors duration-300 ${
        isPlaying ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 
        (isRecording || level !== undefined) ? 'text-white' : 
        'text-zinc-800'
      }`}
      aria-hidden="true"
    >
      {isRecording || isPlaying || level !== undefined ? renderWave() : '................................'}
    </div>
  );
}
