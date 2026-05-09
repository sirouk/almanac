"use client";

import Link from "next/link";
import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

const RESUME_KEY = "arclink_onboarding_resume";

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

  // Inform the backend that checkout was cancelled so the session state
  // is updated. The session can still be resumed via a new onboarding start.
  useEffect(() => {
    if (sessionId) {
      try {
        const raw = window.localStorage.getItem(RESUME_KEY);
        const parsed = raw ? JSON.parse(raw) as { sessionId?: string; cancelToken?: string } : {};
        if (!parsed.sessionId || parsed.sessionId === sessionId) {
          const cancelToken = parsed.cancelToken || "";
          if (cancelToken) api.cancelOnboarding(sessionId, cancelToken).catch(() => {});
        }
      } catch {
        // localStorage can be disabled; leave the session resumable.
      }
    }
  }, [sessionId]);

  // Resume link carries the session ID so the onboarding page can restore
  // the flow from localStorage (which persists) or start fresh.
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
          Your ArcLink onboarding session is preserved. Return when you are ready to bring the agent aboard.
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
