import { useEffect, useRef } from "react";

export const AsciiHalftone = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const parentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = parentRef.current;
    if (!canvas || !parent) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0,
      h = 0;
    let time = 0;
    let animId: number;

    const chars = ".·:+*#@\u2588";
    const CELL = 8;

    function resize() {
      const rect = parent!.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas!.width = w * dpr;
      canvas!.height = h * dpr;
      ctx!.setTransform(1, 0, 0, 1, 0, 0);
      ctx!.scale(dpr, dpr);
    }

    function getIntensity(nx: number, ny: number, t: number) {
      let v = 0;

      v +=
        (Math.sin(nx * 4 + ny * 2 + t * 0.1) *
          Math.cos(nx * 2.5 - ny * 3 + t * 0.08)) *
          0.5 +
        0.5;
      v *= 0.4;

      const angle =
        nx * 3 + ny * 4 + Math.sin(nx * 2 + t * 0.06) * 0.5;
      v += (Math.sin(angle + t * 0.05) * 0.5 + 0.5) * 0.3;

      const sCurve1 =
        ny - (0.5 + Math.sin(nx * Math.PI * 2 + t * 0.12) * 0.25);
      v += Math.exp(-sCurve1 * sCurve1 * 12) * 0.5;

      const sCurve2 =
        ny - (0.3 + Math.cos(nx * Math.PI * 1.5 - t * 0.08) * 0.2);
      v += Math.exp(-sCurve2 * sCurve2 * 18) * 0.35;

      const sCurve3 =
        ny -
        (0.75 + Math.sin(nx * Math.PI * 2.5 + t * 0.06) * 0.12);
      v += Math.exp(-sCurve3 * sCurve3 * 25) * 0.3;

      const cx = 0.6 + Math.sin(t * 0.03) * 0.1;
      const cy = 0.4 + Math.cos(t * 0.04) * 0.1;
      const dist = Math.sqrt((nx - cx) ** 2 + (ny - cy) ** 2);
      v +=
        (Math.sin(dist * 12 + t * 0.08) * 0.5 + 0.5) *
        Math.exp(-dist * 1.5) *
        0.3;

      return Math.min(1, Math.max(0, v));
    }

    function draw() {
      ctx!.clearRect(0, 0, w, h);
      ctx!.font = `${CELL * 0.85}px "Space Mono", monospace`;
      ctx!.textAlign = "center";
      ctx!.textBaseline = "middle";

      for (let y = 0; y < h; y += CELL) {
        for (let x = 0; x < w; x += CELL) {
          const nx = x / w;
          const ny = y / h;
          const intensity = getIntensity(nx, ny, time);

          if (intensity < 0.05) continue;

          const charIdx = Math.min(
            chars.length - 1,
            Math.floor(intensity * chars.length)
          );
          const char = chars[charIdx];
          if (char === " ") continue;

          const alpha = 0.15 + intensity * 0.5;
          const v = 25 + intensity * 35;
          ctx!.fillStyle = `rgba(${v}, ${v}, ${v}, ${alpha})`;
          ctx!.fillText(char, x + CELL / 2, y + CELL / 2);
        }
      }

      time += 0.2;
      animId = requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <div
      ref={parentRef}
      className="absolute inset-0 overflow-hidden z-0 pointer-events-none"
    >
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
};
