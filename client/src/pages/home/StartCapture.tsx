import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { AMBER, ASH, BONE, LINE_D } from "./theme";
import { QUALIFY_EMAIL_KEY, validateWorkEmail } from "./qualify";

/**
 * Inline work-email capture that lives in the hero deck row — visible on
 * landing, no click required. A valid address hands off to /start, where the
 * qualification questions live.
 */
export function StartCapture() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (website) return; // bot
    const emailError = validateWorkEmail(email);
    if (emailError) return setError(emailError);

    const clean = email.trim().toLowerCase();
    // sessionStorage backs the router state so a refresh on /start doesn't
    // lose the address and drop the visitor back to the email question.
    sessionStorage.setItem(QUALIFY_EMAIL_KEY, clean);
    navigate("/start", { state: { email: clean } });
  };

  return (
    <form onSubmit={submit} noValidate className="w-full lg:w-[420px] shrink-0">
      <span
        className="block text-[10.5px] font-mono uppercase tracking-[0.22em] mb-3"
        style={{ color: ASH }}
      >
        Find your starting line
      </span>

      <div
        className="flex items-center gap-3 border-b pb-3 transition-colors focus-within:border-[#A3C57D]"
        style={{ borderColor: error ? AMBER : LINE_D }}
      >
        <input
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (error) setError(null);
          }}
          placeholder="you@company.com"
          aria-label="Work email"
          className="flex-1 min-w-0 bg-transparent text-base outline-none placeholder:opacity-40"
          style={{ color: BONE }}
        />
        <button
          type="submit"
          className="group inline-flex items-center gap-3 shrink-0 cursor-pointer"
        >
          <span
            className="text-[11px] font-mono uppercase tracking-[0.22em]"
            style={{ color: BONE }}
          >
            Get started
          </span>
          <span
            aria-hidden
            className="flex items-center justify-center w-9 h-9 rounded-full border transition-colors duration-200 group-hover:bg-[#A3C57D] group-hover:border-[#A3C57D] group-hover:text-[#0E0E0C]"
            style={{ borderColor: LINE_D, color: ASH }}
          >
            <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
          </span>
        </button>
      </div>

      {/* Honeypot — hidden from humans, catches naive bots. */}
      <input
        type="text"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden
        value={website}
        onChange={(e) => setWebsite(e.target.value)}
        className="absolute opacity-0 pointer-events-none h-0 w-0"
      />

      {error ? (
        <p role="alert" className="text-xs mt-3" style={{ color: AMBER }}>
          {error}
        </p>
      ) : (
        <p className="text-xs mt-3" style={{ color: ASH }}>
          Work email only. Three questions, no sales call.
        </p>
      )}
    </form>
  );
}
