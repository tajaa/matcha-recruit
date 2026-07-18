import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Loader2 } from "lucide-react";
import MarketingFooter from "./MarketingFooter";
import { useSEO } from "../../hooks/useSEO";
import { ASH, BONE, DISPLAY, LINE_D, NOIR } from "../home/theme";
import { GrainOverlay, PageStyle } from "../home/PageChrome";
import {
  HEADCOUNT_OPTIONS,
  LOCATION_OPTIONS,
  NEED_OPTIONS,
  QUALIFY_EMAIL_KEY,
  validateWorkEmail,
} from "../home/qualify";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

export default function StartQualify() {
  const location = useLocation();

  // The hero modal hands the email over in router state; sessionStorage is the
  // fallback so a refresh here doesn't lose it. A visitor who deep-links or
  // shares the URL has neither, so the page collects the email itself rather
  // than bouncing them home.
  const stateEmail = (location.state as { email?: string } | null)?.email;
  const [email, setEmail] = useState(
    () => stateEmail ?? sessionStorage.getItem(QUALIFY_EMAIL_KEY) ?? "",
  );
  const [needsEmail] = useState(() => !email);
  const totalSteps = needsEmail ? 4 : 3;

  // Step indices shift by one when we have to ask for the email first.
  const offset = needsEmail ? 1 : 0;

  const [step, setStep] = useState(0);
  const [headcount, setHeadcount] = useState("");
  const [locations, setLocations] = useState("");
  const [needs, setNeeds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useSEO({
    title: "Find your starting line — Matcha",
    description:
      "A few questions about your headcount, footprint, and exposure. We'll tell you where to begin.",
    canonical: "https://hey-matcha.com/start",
  });

  const next = () => {
    setError(null);
    if (needsEmail && step === 0) {
      const emailError = validateWorkEmail(email);
      if (emailError) return setError(emailError);
      const clean = email.trim().toLowerCase();
      setEmail(clean);
      sessionStorage.setItem(QUALIFY_EMAIL_KEY, clean);
    }
    if (step === offset && !headcount)
      return setError("Pick a range to continue.");
    if (step === offset + 1 && !locations)
      return setError("Pick a range to continue.");
    setStep((s) => Math.min(s + 1, totalSteps - 1));
  };

  const back = () => {
    setError(null);
    setStep((s) => Math.max(s - 1, 0));
  };

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${BASE}/resources/qualify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          headcount_range: headcount,
          location_range: locations,
          primary_needs: needs,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = typeof body?.detail === "string" ? body.detail : null;
        throw new Error(detail ?? "Something went wrong. Try again.");
      }
      sessionStorage.removeItem(QUALIFY_EMAIL_KEY);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleNeed = (value: string) =>
    setNeeds((prev) =>
      prev.includes(value) ? prev.filter((n) => n !== value) : [...prev, value],
    );

  return (
    <div
      style={{ backgroundColor: NOIR, color: BONE }}
      className="min-h-screen flex flex-col overflow-x-hidden"
    >
      <PageStyle />
      <GrainOverlay />

      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 lg:px-16 xl:px-24 pt-[76px] sm:pt-[84px]">
        <div className="grid grid-cols-2 items-center pb-3">
          <Link
            to="/"
            className="text-[10.5px] tracking-[0.28em] font-mono uppercase transition-opacity hover:opacity-60"
            style={{ color: ASH }}
          >
            ← Matcha
          </Link>
          <span
            className="justify-self-end text-[10.5px] tracking-[0.28em] font-mono uppercase tabular-nums"
            style={{ color: ASH }}
          >
            {needsEmail && step === 0 ? "Find your starting line" : email}
          </span>
        </div>
        <div style={{ height: 1, backgroundColor: LINE_D }} />
        <div
          className="mt-[3px]"
          style={{ height: 1, backgroundColor: LINE_D, opacity: 0.45 }}
        />
      </div>

      <main className="flex-1 flex items-center">
        <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 lg:px-16 xl:px-24 py-20">
          <div className="max-w-[820px] mx-auto">
            {done ? (
              <Done email={email} />
            ) : (
              <>
                <Progress step={step} total={totalSteps} />

                <div className="mt-12 min-h-[300px]">
                  {needsEmail && step === 0 && (
                    <Step title="What's your work email?">
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (error) setError(null);
                        }}
                        onKeyDown={(e) => e.key === "Enter" && next()}
                        placeholder="you@company.com"
                        className="w-full max-w-xl bg-transparent border-b pb-3 text-lg outline-none transition-colors focus:border-[#A3C57D] placeholder:opacity-40"
                        style={{ borderColor: LINE_D, color: BONE }}
                      />
                      <p className="text-xs mt-3" style={{ color: ASH }}>
                        Work email only — no Gmail, Outlook, or personal
                        mailboxes.
                      </p>
                    </Step>
                  )}
                  {step === offset && (
                    <Step title="How many employees?">
                      <Choices
                        options={HEADCOUNT_OPTIONS}
                        selected={[headcount]}
                        onSelect={setHeadcount}
                      />
                    </Step>
                  )}
                  {step === offset + 1 && (
                    <Step title="How many places are those employees in?">
                      <Choices
                        options={LOCATION_OPTIONS}
                        selected={[locations]}
                        onSelect={setLocations}
                      />
                    </Step>
                  )}
                  {step === offset + 2 && (
                    <Step title="What's driving this? Pick any that apply.">
                      <Choices
                        options={NEED_OPTIONS}
                        selected={needs}
                        onSelect={toggleNeed}
                        multi
                      />
                    </Step>
                  )}
                </div>

                {error && (
                  <p
                    role="alert"
                    className="text-sm mt-4"
                    style={{ color: "#D97706" }}
                  >
                    {error}
                  </p>
                )}

                <div
                  className="mt-10 pt-7 border-t flex items-center justify-between gap-4"
                  style={{ borderColor: LINE_D }}
                >
                  <button
                    type="button"
                    onClick={back}
                    disabled={step === 0}
                    className="inline-flex items-center gap-2.5 text-[11px] font-mono uppercase tracking-[0.22em] transition-opacity hover:opacity-60 disabled:opacity-0 disabled:pointer-events-none"
                    style={{ color: ASH }}
                  >
                    <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
                    Back
                  </button>

                  <button
                    type="button"
                    onClick={step < totalSteps - 1 ? next : submit}
                    disabled={submitting}
                    className="group inline-flex items-center gap-3.5 disabled:opacity-50"
                  >
                    <span
                      className="text-[11px] font-mono uppercase tracking-[0.22em]"
                      style={{ color: BONE }}
                    >
                      {step < totalSteps - 1
                        ? "Continue"
                        : submitting
                          ? "Sending"
                          : "Get my starting line"}
                    </span>
                    <span
                      aria-hidden
                      className="flex items-center justify-center w-9 h-9 rounded-full border transition-colors duration-200 group-hover:bg-[#A3C57D] group-hover:border-[#A3C57D] group-hover:text-[#0E0E0C]"
                      style={{ borderColor: LINE_D, color: ASH }}
                    >
                      {submitting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
                      )}
                    </span>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </main>

      <div style={{ backgroundColor: BONE, color: "var(--color-ivory-ink)" }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function Progress({ step, total }: { step: number; total: number }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className="h-1.5 rounded-full transition-all duration-300"
          style={{
            width: i === step ? 28 : 8,
            backgroundColor: i <= step ? "#A3C57D" : LINE_D,
          }}
        />
      ))}
      <span
        className="ml-3 text-[10.5px] font-mono uppercase tracking-[0.22em] tabular-nums"
        style={{ color: ASH }}
      >
        {String(step + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
      </span>
    </div>
  );
}

function Step({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h1
        className="tracking-[-0.02em] text-[clamp(1.6rem,3vw,2.6rem)] mb-8"
        style={{ fontFamily: DISPLAY, fontWeight: 300, color: BONE }}
      >
        {title}
      </h1>
      {children}
    </div>
  );
}

function Choices({
  options,
  selected,
  onSelect,
  multi,
}: {
  options: { value: string; label: string; hint?: string }[];
  selected: string[];
  onSelect: (v: string) => void;
  multi?: boolean;
}) {
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      {options.map((opt) => {
        const active = selected.includes(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onSelect(opt.value)}
            aria-pressed={active}
            className="flex items-center justify-between gap-4 text-left border rounded-lg px-5 py-4 transition-colors duration-200"
            style={{
              borderColor: active ? "#A3C57D" : LINE_D,
              backgroundColor: active
                ? "rgba(163,197,125,0.07)"
                : "transparent",
            }}
          >
            <span>
              <span className="block text-base" style={{ color: BONE }}>
                {opt.label}
              </span>
              {opt.hint && (
                <span className="block text-xs mt-0.5" style={{ color: ASH }}>
                  {opt.hint}
                </span>
              )}
            </span>
            {active && (
              <Check
                className="w-4 h-4 shrink-0"
                strokeWidth={2}
                style={{ color: "#A3C57D" }}
              />
            )}
            {multi && !active && (
              <span
                aria-hidden
                className="w-4 h-4 shrink-0 rounded-sm border"
                style={{ borderColor: LINE_D }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

function Done({ email }: { email: string }) {
  return (
    <div className="py-6">
      <h1
        className="tracking-[-0.02em] text-[clamp(1.8rem,3.6vw,3rem)] mb-5"
        style={{ fontFamily: DISPLAY, fontWeight: 300, color: BONE }}
      >
        Got it. We'll be in touch.
      </h1>
      <p className="text-base max-w-xl mb-10" style={{ color: ASH }}>
        We're reading your answers against what we see at companies your size
        and shape. Expect one email at{" "}
        <span style={{ color: BONE }}>{email.trim().toLowerCase()}</span> — a
        starting line, not a pitch deck.
      </p>
      <Link
        to="/"
        className="text-[11px] font-mono uppercase tracking-[0.22em] transition-opacity hover:opacity-60"
        style={{ color: BONE }}
      >
        ← Back to Matcha
      </Link>
    </div>
  );
}
