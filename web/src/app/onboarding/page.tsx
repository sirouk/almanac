"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import { ErrorAlert } from "@/components/ui";

type Step = "start" | "questions" | "checkout" | "done";

const RESUME_KEY = "arclink_onboarding_resume";

type ResumeState = {
  step: Step;
  sessionId: string;
  name: string;
  checkoutUrl: string;
};

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>("start");
  const [name, setName] = useState("");
  const [planId] = useState("starter");
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkoutUrl, setCheckoutUrl] = useState("");
  const [resumed, setResumed] = useState(false);

  // Restore mid-flow state on refresh / Stripe cancel return.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(RESUME_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<ResumeState>;
      if (parsed.sessionId) setSessionId(parsed.sessionId);
      if (parsed.name) setName(parsed.name);
      if (parsed.checkoutUrl) setCheckoutUrl(parsed.checkoutUrl);
      if (parsed.step && parsed.step !== "start") {
        setStep(parsed.step);
        setResumed(true);
      }
    } catch {
      // Stale or corrupt - ignore and start fresh.
    }
  }, []);

  // Persist mid-flow state so a refresh, tab close, or Stripe cancel does not
  // wipe the runner. We never persist the start step (no progress yet).
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (step === "start") return;
    const snapshot: ResumeState = { step, sessionId, name, checkoutUrl };
    try {
      window.localStorage.setItem(RESUME_KEY, JSON.stringify(snapshot));
    } catch {
      // localStorage quota or disabled - drop silently.
    }
  }, [step, sessionId, name, checkoutUrl]);

  function clearResume() {
    try {
      window.localStorage.removeItem(RESUME_KEY);
    } catch {
      // ignore
    }
  }

  function webContactId() {
    const key = "arclink_web_contact_id";
    const existing = window.localStorage.getItem(key);
    if (existing) return existing;
    const generated = `web:${window.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(key, generated);
    return generated;
  }

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.startOnboarding({ channel: "web", channel_identity: webContactId(), plan_id: planId });
      if (res.status === 201 && res.data) {
        const session = (res.data as Record<string, Record<string, string>>).session;
        setSessionId(session.session_id);
        setStep("questions");
      } else {
        setError((res.data as Record<string, string>).error || "Failed to start onboarding");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnswer(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.answerOnboarding({
        session_id: sessionId,
        question_key: "name",
        answer_summary: name,
        display_name: name,
      });
      if (res.status === 200) {
        setStep("checkout");
      } else {
        setError((res.data as Record<string, string>).error || "Failed to save answer");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCheckout() {
    setError("");
    setLoading(true);
    try {
      const res = await api.openCheckout({
        session_id: sessionId,
        success_url: window.location.origin + "/dashboard?session=" + encodeURIComponent(sessionId),
        cancel_url: window.location.origin + "/onboarding?resume=1",
      });
      if (res.status === 200) {
        const session = (res.data as Record<string, Record<string, string>>).session;
        const url = session?.checkout_url || (res.data as Record<string, string>).checkout_url;
        if (url) {
          setCheckoutUrl(url);
        }
        setStep("done");
      } else {
        setError((res.data as Record<string, string>).error || "Checkout failed");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6">
      <Link href="/" className="mb-8 font-display text-xl font-bold tracking-wide">
        <span className="text-signal-orange">ARC</span>LINK
      </Link>

      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-8">
        <Image
          src="/brand/raven/raven_pfp.webp"
          alt=""
          width={64}
          height={64}
          className="mb-5 h-16 w-16 rounded-full border border-border object-cover"
          unoptimized
          priority
        />
        <p className="mb-2 text-xs uppercase tracking-[0.22em] text-soft-white/40">
          {step === "start" && "Step 1 of 4 - First contact"}
          {step === "questions" && "Step 2 of 4 - Name on the hatch"}
          {step === "checkout" && "Step 3 of 4 - Stripe handoff"}
          {step === "done" && "Step 4 of 4 - Launch queue"}
        </p>
        <h1 className="font-display text-2xl font-bold">
          {step === "start" && "I'm Raven"}
          {step === "questions" && "Name On The Hatch"}
          {step === "checkout" && "Hire My First Agent"}
          {step === "done" && "Stripe Link Ready"}
        </h1>

        {error && <ErrorAlert message={error} className="mt-4" />}

        {resumed && step !== "start" && step !== "done" && (
          <p className="mt-4 rounded border border-border bg-carbon/60 px-3 py-2 text-xs text-soft-white/70">
            Welcome back. I held your place - pick up where you left off.
          </p>
        )}

        {step === "start" && (
          <form onSubmit={handleStart} className="mt-6 space-y-4">
            <p className="text-sm text-soft-white/60">
              I can take you from a few answers to a private AI agent of your own - with memory, document retrieval, files, a code workspace, and a live dashboard already wired up. Stripe collects your email securely at checkout. No technical setup on your end.
            </p>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Opening..." : "Start Launch"}
            </button>
          </form>
        )}

        {step === "questions" && (
          <form onSubmit={handleAnswer} className="mt-6 space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm text-soft-white/60">Display Name</label>
              <input
                id="name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-soft-white outline-none focus:border-signal-orange"
                placeholder="Your name or org"
              />
            </div>
            <p className="text-sm text-soft-white/40">
              Starter puts your first ArcLink agent aboard for <span className="text-signal-orange">$35/month</span>. After launch, I can add more agents for $15/month each.
            </p>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Saving..." : "Save & Continue"}
            </button>
          </form>
        )}

        {step === "checkout" && (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-soft-white/60">
              I will hand you to Stripe, watch for confirmation, then move your first ArcLink agent from idea to launch queue.
            </p>
            <button
              onClick={handleCheckout}
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Preparing..." : "Hire My First Agent - $35/mo"}
            </button>
          </div>
        )}

        {step === "done" && (
          <div className="mt-6 space-y-4">
            {checkoutUrl ? (
              <>
                <p className="text-sm text-soft-white/60">
                  I have your checkout link ready.
                </p>
                <a
                  href={checkoutUrl}
                  onClick={clearResume}
                  className="block w-full rounded bg-signal-orange px-4 py-2 text-center font-semibold text-jet transition hover:opacity-90"
                >
                  Complete The Hire
                </a>
              </>
            ) : (
              <>
                <p className="text-sm text-neon-green">
                  Onboarding complete. I am preparing your deployment.
                </p>
                <Link
                  href="/dashboard"
                  className="block w-full rounded bg-signal-orange px-4 py-2 text-center font-semibold text-jet transition hover:opacity-90"
                >
                  Open Dashboard →
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      <p className="mt-6 text-xs text-soft-white/30">
        Fake adapters active in development. No live charges.
      </p>
    </div>
  );
}
