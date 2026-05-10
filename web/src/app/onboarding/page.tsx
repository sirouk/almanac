"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import { ErrorAlert } from "@/components/ui";

type Step = "start" | "questions" | "checkout" | "done";
type PlanId = "founders" | "sovereign" | "scale";

const RESUME_KEY = "arclink_onboarding_resume";

type ResumeState = {
  step: Step;
  sessionId: string;
  claimToken: string;
  cancelToken: string;
  name: string;
  email: string;
  planId: PlanId;
  checkoutUrl: string;
};

const PLAN_COPY: Record<PlanId, { name: string; price: string; summary: string; checkout: string }> = {
  founders: {
    name: "Limited 100 Founders",
    price: "$149/month",
    summary: "Agent onboard ArcLink for the first 100.",
    checkout: "Onboard Agent - $149/month",
  },
  sovereign: {
    name: "Sovereign",
    price: "$199/month",
    summary: "Agent onboard ArcLink.",
    checkout: "Onboard Agent - $199/month",
  },
  scale: {
    name: "Scale",
    price: "$275/month",
    summary: "Agents onboard ArcLink with Federation.",
    checkout: "Onboard Agents - $275/month",
  },
};

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>("start");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [planId, setPlanId] = useState<PlanId>("founders");
  const [showStandardPlans, setShowStandardPlans] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [claimToken, setClaimToken] = useState("");
  const [cancelToken, setCancelToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkoutUrl, setCheckoutUrl] = useState("");
  const [resumed, setResumed] = useState(false);
  const [fakeMode, setFakeMode] = useState<boolean | null>(null);

  useEffect(() => {
    api.adapterMode().then((r) => {
      if (r.status === 200) setFakeMode((r.data as { fake_mode?: boolean }).fake_mode ?? null);
    }).catch(() => {});
  }, []);

  // Restore mid-flow state on refresh / Stripe cancel return.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(RESUME_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<ResumeState>;
      if (parsed.sessionId) setSessionId(parsed.sessionId);
      if (parsed.claimToken) setClaimToken(parsed.claimToken);
      if (parsed.cancelToken) setCancelToken(parsed.cancelToken);
      if (parsed.name) setName(parsed.name);
      if (parsed.email) setEmail(parsed.email);
      if (parsed.planId === "founders" || parsed.planId === "sovereign" || parsed.planId === "scale") setPlanId(parsed.planId);
      if (parsed.checkoutUrl) setCheckoutUrl(parsed.checkoutUrl);
      if (parsed.step && parsed.step !== "start") {
        const isCheckoutResume = new URLSearchParams(window.location.search).get("resume") === "1";
        setStep(isCheckoutResume && parsed.step === "done" ? "checkout" : parsed.step);
        if (isCheckoutResume && parsed.step === "done") setCheckoutUrl("");
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
    const snapshot: ResumeState = { step, sessionId, claimToken, cancelToken, name, email, planId, checkoutUrl };
    try {
      window.localStorage.setItem(RESUME_KEY, JSON.stringify(snapshot));
    } catch {
      // localStorage quota or disabled - drop silently.
    }
  }, [step, sessionId, claimToken, cancelToken, name, email, planId, checkoutUrl]);

  function webContactId() {
    const key = "arclink_web_contact_id";
    const existing = window.localStorage.getItem(key);
    if (existing) return existing;
    const generated = `web:${window.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(key, generated);
    return generated;
  }

  async function handleStart(nextPlanId: PlanId) {
    setError("");
    setPlanId(nextPlanId);
    setLoading(true);
    try {
      const res = await api.startOnboarding({ channel: "web", channel_identity: webContactId(), plan_id: nextPlanId, email });
      if (res.status === 201 && res.data) {
        const payload = res.data as Record<string, unknown>;
        const session = payload.session as Record<string, string>;
        setSessionId(session.session_id);
        setClaimToken(String(payload.browser_claim_token || ""));
        setCancelToken(String(payload.browser_cancel_token || ""));
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
        success_url: window.location.origin + "/checkout/success?session=" + encodeURIComponent(sessionId),
        cancel_url: window.location.origin + "/checkout/cancel?session=" + encodeURIComponent(sessionId),
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
          {step === "questions" && "Step 2 of 4 - Name the agent"}
          {step === "checkout" && "Step 3 of 4 - Stripe handoff"}
          {step === "done" && "Step 4 of 4 - Launch queue"}
        </p>
        <h1 className="font-display text-2xl font-bold">
          {step === "start" && "Choose ArcLink Onboarding"}
          {step === "questions" && "Name The Agent"}
          {step === "checkout" && PLAN_COPY[planId].checkout}
          {step === "done" && "Stripe Link Ready"}
        </h1>

        {error && <ErrorAlert message={error} className="mt-4" />}

        {resumed && step !== "start" && step !== "done" && (
          <p className="mt-4 rounded border border-border bg-carbon/60 px-3 py-2 text-xs text-soft-white/70">
            Welcome back. I held your place - pick up where you left off.
          </p>
        )}

        {step === "start" && (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-soft-white/60">
              I can take you from a few answers to agent onboard ArcLink with memory, files, code workspace, model access, and dashboard visibility already wired up.
            </p>
            <div className="grid gap-3">
              {!showStandardPlans ? (
                <>
                  <button
                    type="button"
                    onClick={() => handleStart("founders")}
                    disabled={loading}
                    className="rounded border border-signal-orange bg-signal-orange px-4 py-3 text-left font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
                  >
                    Founders - $149/month
                    <span className="mt-1 block text-xs font-normal text-jet/70">Limited to the first 100. Agent onboard ArcLink.</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowStandardPlans(true)}
                    disabled={loading}
                    className="rounded border border-border bg-carbon px-4 py-3 text-left font-semibold text-soft-white transition hover:border-signal-orange disabled:opacity-50"
                  >
                    Sovereign / Scale
                    <span className="mt-1 block text-xs font-normal text-soft-white/60">Compare agent onboarding options.</span>
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => handleStart("sovereign")}
                    disabled={loading}
                    className="rounded border border-signal-orange bg-signal-orange px-4 py-3 text-left font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
                  >
                    Sovereign - $199/month
                    <span className="mt-1 block text-xs font-normal text-jet/70">Agent onboard ArcLink.</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleStart("scale")}
                    disabled={loading}
                    className="rounded border border-border bg-carbon px-4 py-3 text-left font-semibold text-soft-white transition hover:border-signal-orange disabled:opacity-50"
                  >
                    Scale - $275/month
                    <span className="mt-1 block text-xs font-normal text-soft-white/60">Agents onboard ArcLink with Federation.</span>
                  </button>
                </>
              )}
            </div>
          </div>
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
              <p className="mt-1 text-xs text-soft-white/30">Used for login and status after checkout.</p>
            </div>
            <p className="text-sm text-soft-white/40">
              {PLAN_COPY[planId].name} is on deck at <span className="text-signal-orange">{PLAN_COPY[planId].price}</span>. {PLAN_COPY[planId].summary} Agentic Expansion is $99/month on Sovereign and $79/month on Scale.
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
              I will hand you to Stripe, watch for confirmation, then move your ArcLink onboarding into the launch queue.
            </p>
            <button
              onClick={handleCheckout}
              disabled={loading}
              className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Preparing..." : PLAN_COPY[planId].checkout}
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
                  Open Dashboard
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      {fakeMode === true && (
        <p className="mt-6 text-xs text-soft-white/30">
          Fake adapters active in development. No live charges.
        </p>
      )}
    </div>
  );
}
