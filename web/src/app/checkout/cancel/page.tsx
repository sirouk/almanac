"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

const RESUME_KEY = "arclink_onboarding_resume";
const PROOF_STORAGE_KEY = "arclink_onboarding_proof";

type ResumeState = {
  step?: "start" | "questions" | "checkout" | "done";
  sessionId?: string;
  name?: string;
  agentName?: string;
  agentTitle?: string;
  email?: string;
  planId?: "founders" | "sovereign" | "scale";
  checkoutUrl?: string;
};

export default function CheckoutCancelPage() {
  return (
    <Suspense fallback={<CheckoutCancelFallback />}>
      <CheckoutCancelContent />
    </Suspense>
  );
}

function CheckoutCancelFallback() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-soft-white/40">
          Checkout paused
        </p>
        <h1 className="font-display text-3xl font-bold">No charge completed</h1>
        <p className="mt-4 text-sm text-soft-white/65">
          Loading checkout state...
        </p>
      </section>
    </main>
  );
}

function CheckoutCancelContent() {
  const params = useSearchParams();
  const sessionId = params.get("session") || "";
  const [cancelState, setCancelState] = useState<"idle" | "done" | "unavailable">("idle");

  useEffect(() => {
    if (!sessionId) return;
    let cancelToken = params.get("cancel_token") || "";
    if (!cancelToken) {
      try {
        const raw = window.sessionStorage.getItem(PROOF_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) as { sessionId?: string; cancelToken?: string } : {};
        if (parsed.sessionId === sessionId) cancelToken = parsed.cancelToken || "";
      } catch {
        cancelToken = "";
      }
    }
    if (!cancelToken) {
      setCancelState("unavailable");
      return;
    }
    api.cancelOnboarding(sessionId, cancelToken)
      .then((res) => {
        const cancelled = res.status === 200;
        setCancelState(cancelled ? "done" : "unavailable");
        if (cancelled) resetResumeAfterCancel(sessionId);
      })
      .catch(() => setCancelState("unavailable"))
      .finally(() => {
        try {
          window.sessionStorage.removeItem(PROOF_STORAGE_KEY);
        } catch {
          // ignore
        }
      });
  }, [params, sessionId]);

  // Resume link carries the session ID for recovery, but proof material is
  // session-only and is cleared after the cancel request is attempted.
  const resumeHref = sessionId
    ? `/onboarding?resume=1&session=${encodeURIComponent(sessionId)}`
    : "/onboarding?resume=1";

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-soft-white/40">
          Checkout paused
        </p>
        <h1 className="font-display text-3xl font-bold">No charge completed</h1>
        <p className="mt-4 text-sm text-soft-white/65">
          {cancelState === "done"
            ? "Your checkout was cancelled and ArcLink marked this onboarding session as payment-cancelled."
            : "Your checkout was paused before payment completed. Return when you are ready to bring the agent aboard."}
        </p>
        {sessionId && (
          <p className="mt-2 text-xs text-soft-white/30">
            Session: {sessionId.slice(0, 12)}...
          </p>
        )}
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href={resumeHref}
            className="rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90"
          >
            Resume Onboarding
          </Link>
          <Link
            href="/"
            className="rounded border border-border px-4 py-2 font-semibold text-soft-white transition hover:bg-carbon"
          >
            Back Home
          </Link>
        </div>
      </section>
    </main>
  );
}

function resetResumeAfterCancel(sessionId: string) {
  try {
    const raw = window.localStorage.getItem(RESUME_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as ResumeState;
    if (parsed.sessionId !== sessionId) return;
    const planId = parsed.planId === "founders" || parsed.planId === "sovereign" || parsed.planId === "scale"
      ? parsed.planId
      : undefined;
    const next: ResumeState = {
      step: "start",
      sessionId: "",
      name: parsed.name || "",
      agentName: parsed.agentName || "",
      agentTitle: parsed.agentTitle || "",
      email: parsed.email || "",
      planId,
      checkoutUrl: "",
    };
    window.localStorage.setItem(RESUME_KEY, JSON.stringify(next));
  } catch {
    // Resume storage is best-effort; cancellation itself has already run.
  }
}
