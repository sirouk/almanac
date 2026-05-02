"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import { ErrorAlert } from "@/components/ui";

type Step = "start" | "questions" | "checkout" | "done";

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>("start");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [planId] = useState("starter");
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkoutUrl, setCheckoutUrl] = useState("");

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.startOnboarding({ channel: "web", email, plan_id: planId });
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
        email,
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
        price_id: "price_arclink_starter",
        success_url: window.location.origin + "/dashboard",
        cancel_url: window.location.origin + "/onboarding",
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
        <h1 className="font-display text-2xl font-bold">
          {step === "start" && "Start Your Deployment"}
          {step === "questions" && "Tell Us About You"}
          {step === "checkout" && "Activate Your Plan"}
          {step === "done" && "You're All Set"}
        </h1>

        {error && <ErrorAlert message={error} className="mt-4" />}

        {step === "start" && (
          <form onSubmit={handleStart} className="mt-6 space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm text-soft-white/60">Email</label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-soft-white outline-none focus:border-signal-orange"
                placeholder="you@company.com"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Starting..." : "Continue →"}
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
              Plan: <span className="text-signal-orange">Starter</span>
            </p>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Saving..." : "Continue to Checkout →"}
            </button>
          </form>
        )}

        {step === "checkout" && (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-soft-white/60">
              Ready to activate your ArcLink Starter deployment. You&apos;ll be redirected to
              Stripe for secure payment.
            </p>
            <button
              onClick={handleCheckout}
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Preparing..." : "Activate & Pay →"}
            </button>
          </div>
        )}

        {step === "done" && (
          <div className="mt-6 space-y-4">
            {checkoutUrl ? (
              <>
                <p className="text-sm text-soft-white/60">
                  Your checkout session is ready.
                </p>
                <a
                  href={checkoutUrl}
                  className="block w-full rounded bg-signal-orange px-4 py-2 text-center font-semibold text-jet transition hover:opacity-90"
                >
                  Complete Payment →
                </a>
              </>
            ) : (
              <>
                <p className="text-sm text-neon-green">
                  Onboarding complete. Your deployment is being prepared.
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
