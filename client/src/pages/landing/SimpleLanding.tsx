import { useEffect, useState } from "react";

const LINES = ["matcha technologies", "for info contact aaron@hey-matcha.com"];
const TYPE_MS = 80;
const HOLD_MS = 1400;
const ERASE_MS = 30;

export default function SimpleLanding() {
  const [lineIndex, setLineIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const [phase, setPhase] = useState("typing"); // "typing" | "holding" | "erasing"

  useEffect(() => {
    const line = LINES[lineIndex];

    if (phase === "typing") {
      if (typed.length < line.length) {
        const t = setTimeout(() => setTyped(line.slice(0, typed.length + 1)), TYPE_MS);
        return () => clearTimeout(t);
      }
      const t = setTimeout(() => setPhase("holding"), HOLD_MS);
      return () => clearTimeout(t);
    }

    if (phase === "holding") {
      const t = setTimeout(() => setPhase("erasing"), 0);
      return () => clearTimeout(t);
    }

    if (phase === "erasing") {
      if (typed.length > 0) {
        const t = setTimeout(() => setTyped(typed.slice(0, -1)), ERASE_MS);
        return () => clearTimeout(t);
      }
      setLineIndex((i) => (i + 1) % LINES.length);
      setPhase("typing");
    }
  }, [phase, typed, lineIndex]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-black">
      <pre className="font-mono text-2xl text-green-400">
        {"$ "}
        {typed}
        <span className="animate-pulse">_</span>
      </pre>
    </div>
  );
}
