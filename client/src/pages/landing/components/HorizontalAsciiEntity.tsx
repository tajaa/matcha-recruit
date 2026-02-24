import { memo, useEffect, useRef } from "react";

export const HorizontalAsciiEntity = memo(() => {
  const preRef = useRef<HTMLPreElement>(null);
  const phaseRef = useRef(0);

  useEffect(() => {
    let animationFrameId: number;
    let lastTime = performance.now();
    const fps = 15; // Limit FPS to save CPU
    const interval = 1000 / fps;

    const generateLines = (phase: number) => {
      let result = "";
      for (let i = 0; i < 24; i++) {
        const offset = Math.sin((i + phase * 0.5) * 0.2) * 10;
        const width = Math.max(10, 30 + Math.sin((i - phase * 0.3) * 0.4) * 20);
        const char = width > 40 ? "━" : width > 25 ? "─" : "-";
        const padding = " ".repeat(Math.max(0, Math.floor(20 + offset)));
        result += padding + char.repeat(Math.floor(width)) + "\n";
      }
      return result;
    };

    const animate = (time: number) => {
      animationFrameId = requestAnimationFrame(animate);
      const deltaTime = time - lastTime;

      if (deltaTime > interval) {
        lastTime = time - (deltaTime % interval);
        phaseRef.current += 1;
        if (preRef.current) {
          preRef.current.textContent = generateLines(phaseRef.current);
        }
      }
    };

    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  return (
    <div className="relative group">
      <div
        className="absolute inset-0 bg-[#4ADE80] opacity-10 blur-[40px] rounded-full group-hover:opacity-20 transition-opacity duration-1000"
        style={{ transform: "translateZ(0)" }}
      />
      <pre
        ref={preRef}
        className="relative z-10 font-mono text-[10px] leading-[0.6] tracking-tighter text-[#4ADE80] select-none whitespace-pre"
        style={{
          textShadow: "0 0 10px rgba(74, 222, 128, 0.4)",
          transform: "translateZ(0)",
        }}
      />
      <div className="absolute top-0 right-0 text-[#F0EFEA]/30 text-[8px] font-mono uppercase tracking-[0.3em]">
        Neural Entity
      </div>
    </div>
  );
});
