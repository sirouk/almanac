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
  const [selectedChannel, setSelectedChannel] = useState("web");
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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedPlan = params.get("plan");
    const requestedChannel = params.get("channel");
    if (requestedPlan === "founders" || requestedPlan === "sovereign" || requestedPlan === "scale") {
      setPlanId(requestedPlan);
      if (requestedPlan !== "founders") setShowStandardPlans(true);
    }
    if (requestedChannel === "telegram" || requestedChannel === "discord") {
      setSelectedChannel(requestedChannel);
    }
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

  async function openCheckoutForSession(nextSessionId = sessionId) {
    setError("");
    setLoading(true);
    try {
      const res = await api.openCheckout({
        session_id: nextSessionId,
        success_url: window.location.origin + "/checkout/success?session=" + encodeURIComponent(nextSessionId),
        cancel_url: window.location.origin + "/checkout/cancel?session=" + encodeURIComponent(nextSessionId),
      });
      if (res.status === 200) {
        const session = (res.data as Record<string, Record<string, string>>).session;
        const url = session?.checkout_url || (res.data as Record<string, string>).checkout_url;
        if (url) {
          setCheckoutUrl(url);
          setStep("done");
          return true;
        }
        setStep("checkout");
        setError("Stripe did not return a checkout link. Try again.");
        return false;
      } else {
        setStep("checkout");
        setError((res.data as Record<string, string>).error || "Checkout failed");
        return false;
      }
    } catch {
      setError("Network error. Please try again.");
      setStep("checkout");
      return false;
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
        setLoading(false);
        await openCheckoutForSession(sessionId);
      } else {
        setError((res.data as Record<string, string>).error || "Failed to save answer");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#080808] px-6 py-8">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(251,80,5,0.032) 1px, transparent 1px), linear-gradient(90deg, rgba(251,80,5,0.026) 1px, transparent 1px)",
          backgroundSize: "80px 80px",
        }}
      />
      <div className="scan-line-hero" style={{ animationDelay: "1s" }} />

      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between">
        <Link href="/" aria-label="ArcLink home">
          <Image
            src="/marketing/Arclink_v3--orange_symbol_white_text.svg"
            alt="ArcLink"
            width={154}
            height={32}
            className="h-8 w-auto"
            priority
          />
        </Link>
        <Link
          href="/login"
          className="rounded border border-white/10 px-4 py-2 font-mono text-xs font-semibold tracking-widest text-[#E7E6E6]/60 transition hover:border-[#FB5005]/35 hover:text-[#E7E6E6]"
        >
          LOGIN
        </Link>
      </header>

      <main className="relative z-10 mx-auto grid min-h-[calc(100vh-96px)] max-w-6xl items-center gap-10 py-14 lg:grid-cols-[0.9fr_1.1fr]">
        <section className="hidden lg:block">
          <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#FB5005]/70">Raven onboarding</p>
          <h1 className="font-heading mt-5 max-w-xl text-5xl font-normal leading-[1.04] text-[#E7E6E6]">
            Pick the first agent. Raven handles the handoff.
          </h1>
          <p className="font-body mt-6 max-w-lg text-base leading-relaxed text-[#E7E6E6]/50">
            The web flow keeps the Stripe and dashboard pieces in one place, then Raven continues the setup in your preferred channel.
          </p>
          <div className="mt-8 grid max-w-lg grid-cols-3 gap-px overflow-hidden rounded-lg bg-white/5">
            {[
              ["01", "Plan"],
              ["02", "Identity"],
              ["03", "Stripe"],
            ].map(([num, label]) => (
              <div key={num} className="bg-[#0F0F0E] px-5 py-4">
                <p className="font-heading text-2xl font-bold text-[#FB5005]/70">{num}</p>
                <p className="font-mono mt-1 text-[10px] uppercase tracking-widest text-[#E7E6E6]/35">{label}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto w-full max-w-md rounded-lg border border-white/8 bg-[#0F0F0E]/95 p-8 shadow-[0_0_70px_rgba(251,80,5,0.08)] backdrop-blur">
          <Image
            src="/marketing/Favicon.png"
            alt=""
            width={64}
            height={64}
            className="mb-5 h-16 w-16 rounded-lg border border-white/10 object-cover"
            unoptimized
            priority
          />
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.25em] text-[#E7E6E6]/35">
            {step === "start" && "Step 1 of 3 - First contact"}
            {step === "questions" && "Step 2 of 3 - Name and contact"}
            {step === "checkout" && "Step 3 of 3 - Stripe handoff"}
            {step === "done" && "Step 3 of 3 - Stripe handoff"}
          </p>
          <h2 className="font-heading text-3xl font-normal text-[#E7E6E6]">
            {step === "start" && "Choose ArcLink Onboarding"}
            {step === "questions" && "Name The Agent"}
            {step === "checkout" && PLAN_COPY[planId].checkout}
            {step === "done" && "Stripe Handoff Ready"}
          </h2>

          {selectedChannel !== "web" && step === "start" && (
            <p className="mt-3 rounded border border-[#FB5005]/20 bg-[#FB5005]/5 px-3 py-2 font-body text-xs text-[#E7E6E6]/55">
              Preferred channel: <span className="capitalize text-[#FB5005]">{selectedChannel}</span>. Raven will continue there after checkout.
            </p>
          )}

          {error && <ErrorAlert message={error} className="mt-4" />}

          {resumed && step !== "start" && step !== "done" && (
            <p className="mt-4 rounded border border-white/10 bg-[#080808]/60 px-3 py-2 text-xs text-[#E7E6E6]/70">
              Welcome back. I held your place - pick up where you left off.
            </p>
          )}

          {step === "start" && (
            <div className="mt-6 space-y-4">
              <p className="font-body text-sm leading-relaxed text-[#E7E6E6]/55">
                I can take you from a few answers to agent onboard ArcLink with memory, files, code workspace, model access, and dashboard visibility already wired up.
              </p>
              <div className="grid gap-3">
                {!showStandardPlans ? (
                  <>
                    <button
                      type="button"
                      onClick={() => handleStart("founders")}
                      disabled={loading}
                      className="rounded border border-[#FB5005] bg-[#FB5005] px-4 py-3 text-left font-body font-semibold text-white transition hover:bg-[#e04504] disabled:opacity-50"
                    >
                      Founders - $149/month
                      <span className="mt-1 block text-xs font-normal text-white/70">Limited to the first 100. Agent onboard ArcLink.</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowStandardPlans(true)}
                      disabled={loading}
                      className="rounded border border-white/10 bg-[#080808] px-4 py-3 text-left font-body font-semibold text-[#E7E6E6] transition hover:border-[#FB5005]/40 disabled:opacity-50"
                    >
                      Sovereign / Scale
                      <span className="mt-1 block text-xs font-normal text-[#E7E6E6]/50">Compare agent onboarding options.</span>
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => handleStart("sovereign")}
                      disabled={loading}
                      className="rounded border border-[#FB5005] bg-[#FB5005] px-4 py-3 text-left font-body font-semibold text-white transition hover:bg-[#e04504] disabled:opacity-50"
                    >
                      Sovereign - $199/month
                      <span className="mt-1 block text-xs font-normal text-white/70">Agent onboard ArcLink.</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleStart("scale")}
                      disabled={loading}
                      className="rounded border border-white/10 bg-[#080808] px-4 py-3 text-left font-body font-semibold text-[#E7E6E6] transition hover:border-[#FB5005]/40 disabled:opacity-50"
                    >
                      Scale - $275/month
                      <span className="mt-1 block text-xs font-normal text-[#E7E6E6]/50">Agents onboard ArcLink with Federation.</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {step === "questions" && (
            <form onSubmit={handleAnswer} className="mt-6 space-y-4">
              <div>
                <label htmlFor="name" className="font-body block text-sm text-[#E7E6E6]/55">Display Name</label>
                <input
                  id="name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 w-full rounded border border-white/10 bg-[#080808] px-3 py-2 text-[#E7E6E6] outline-none transition focus:border-[#FB5005]"
                  placeholder="Your name or org"
                />
              </div>
              <div>
                <label htmlFor="email" className="font-body block text-sm text-[#E7E6E6]/55">Email</label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full rounded border border-white/10 bg-[#080808] px-3 py-2 text-[#E7E6E6] outline-none transition focus:border-[#FB5005]"
                  placeholder="you@company.com"
                />
                <p className="mt-1 text-xs text-[#E7E6E6]/30">Used for login and status after checkout.</p>
              </div>
              <p className="font-body text-sm text-[#E7E6E6]/40">
                {PLAN_COPY[planId].name} is on deck at <span className="text-[#FB5005]">{PLAN_COPY[planId].price}</span>. {PLAN_COPY[planId].summary} Agentic Expansion is $99/month on Sovereign and $79/month on Scale.
              </p>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded bg-[#FB5005] px-4 py-3 font-body font-semibold text-white transition hover:bg-[#e04504] disabled:opacity-50"
              >
                {loading ? "Preparing Stripe..." : "Continue To Stripe"}
              </button>
            </form>
          )}

          {step === "checkout" && (
            <div className="mt-6 space-y-4">
              <p className="font-body text-sm text-[#E7E6E6]/55">
                I will hand you to Stripe, watch for confirmation, then move your ArcLink onboarding into the launch queue.
              </p>
              <button
                onClick={() => openCheckoutForSession()}
                disabled={loading}
                className="w-full rounded bg-[#FB5005] px-4 py-3 font-body font-semibold text-white transition hover:bg-[#e04504] disabled:opacity-50"
              >
                {loading ? "Preparing..." : PLAN_COPY[planId].checkout}
              </button>
            </div>
          )}

          {step === "done" && (
            <div className="mt-6 space-y-4">
              {checkoutUrl ? (
                <>
                  <p className="font-body text-sm text-[#E7E6E6]/55">
                    Stage 1 is ready: finish the Stripe handoff. When payment clears, Raven starts provisioning and reports the result with your working links.
                  </p>
                  <a
                    href={checkoutUrl}
                    className="block w-full rounded bg-[#FB5005] px-4 py-3 text-center font-body font-semibold text-white transition hover:bg-[#e04504]"
                  >
                    Complete The Hire
                  </a>
                </>
              ) : (
                <>
                  <p className="font-body text-sm text-[#1AC153]">
                    Onboarding complete. I am preparing your deployment.
                  </p>
                  <Link
                    href="/dashboard"
                    className="block w-full rounded bg-[#FB5005] px-4 py-3 text-center font-body font-semibold text-white transition hover:bg-[#e04504]"
                  >
                    Open Dashboard
                  </Link>
                </>
              )}
            </div>
          )}

          {fakeMode === true && (
            <p className="mt-6 font-body text-xs text-[#E7E6E6]/30">
              Fake adapters active in development. No live charges.
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
