import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { AMBER, ASH, BONE, LEAF, LINE_D, NOIR, SURFACE } from "./theme";
import { EYEBROW } from "./layout";
import { QUALIFY_EMAIL_KEY, validateWorkEmail } from "./qualify";

/**
 * Inline work-email capture that lives in the hero deck row — visible on
 * landing, no click required. A valid address hands off to /start, where the
 * qualification questions live.
 *
 * Treatment: a filled composite (raised surface + leaf-filled submit), and it
 * is the ONLY filled-solid element above the fold. That is where its primacy
 * comes from — being the sole member of its class, not being loud. The previous
 * version was a transparent input on a hairline with an 11px mono label and an
 * outlined icon circle, which read as *quieter* than the nav's outlined
 * "Request Demo" pill: the secondary CTA out-weighted the primary one.
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
    // `relative` is load-bearing: the honeypot below is absolutely positioned
    // and would otherwise escape to the nearest positioned ancestor.
    <form onSubmit={submit} noValidate className="relative w-full">
      <span className={`block mb-3 ${EYEBROW}`} style={{ color: ASH }}>
        Find your starting line
      </span>

      <div
        className="flex items-center gap-2 rounded-full border pl-5 pr-1.5 transition-colors duration-200 focus-within:border-[#A3C57D]"
        style={{
          height: 56,
          backgroundColor: SURFACE,
          borderColor: error ? AMBER : LINE_D,
        }}
      >
        <input
          type="email"
          // name/autoComplete/inputMode were all absent, which suppressed
          // browser autofill on the page's only conversion field.
          name="email"
          autoComplete="email"
          inputMode="email"
          enterKeyHint="go"
          // iOS Safari capitalises the first letter and runs autocorrect on a
          // bare text-ish input, so a tapped address arrives as "You@company"
          // and fails validateWorkEmail. `type="email"` alone does not suppress
          // either on iOS — these three attributes are what do it.
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (error) setError(null);
          }}
          placeholder="you@company.com"
          aria-label="Work email"
          aria-invalid={!!error}
          className="flex-1 min-w-0 bg-transparent text-base outline-none placeholder:opacity-40"
          style={{ color: BONE }}
        />
        <button
          type="submit"
          className="group inline-flex items-center gap-2 shrink-0 h-11 pl-5 pr-4 rounded-full text-[14px] font-medium cursor-pointer transition-all duration-200 hover:brightness-110 active:brightness-95"
          style={{ backgroundColor: LEAF, color: NOIR }}
        >
          {/* The long label only fits once the deck row has real width. At the
              `md:` two-column step the capture is 360px, and the full label
              squeezed the input to a truncated "you@company." */}
          <span className="hidden lg:inline">Find my starting line</span>
          <span className="lg:hidden">Start</span>
          <ArrowRight
            aria-hidden
            className="w-4 h-4 shrink-0 transition-transform duration-200 group-hover:translate-x-0.5"
            strokeWidth={2}
          />
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

      {/* min-h reserves the helper line's height so surfacing an error doesn't
          reflow the fold by one line. */}
      <div className="mt-3 min-h-[1.25rem]">
        {error ? (
          <p role="alert" className="text-xs" style={{ color: AMBER }}>
            {error}
          </p>
        ) : (
          <p className="text-xs" style={{ color: ASH }}>
            Work email only. Three questions, no sales call.
          </p>
        )}
      </div>
    </form>
  );
}
