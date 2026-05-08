"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { StatusBadge, LoadingSpinner } from "@/components/ui";

const RESUME_KEY = "arclink_onboarding_resume";
const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 40; // ~2 minutes

type EntitlementStatus = "unknown" | "pending" | "paid" | "failed";

export default function CheckoutSuccessPage() {
  return (
    <Suspense fallback={<CheckoutSuccessFallback />}>
      <CheckoutSuccessContent />
    </Suspense>
  );
}

function CheckoutSuccessFallback() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-signal-orange">
          Verifying payment
        </p>
        <h1 className="font-display text-3xl font-bold">Waiting for confirmation</h1>
        <div className="mt-4 flex items-center gap-3">
          <LoadingSpinner label="" />
          <p className="text-sm text-soft-white/65">
            Loading checkout status...
          </p>
        </div>
      </section>
    </main>
  );
}

function CheckoutSuccessContent() {
  const params = useSearchParams();
  const sessionId = params.get("session") || "";
  const [status, setStatus] = useState<EntitlementStatus>("pending");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [sessionClaimed, setSessionClaimed] = useState(false);
  const [pollCount, setPollCount] = useState(0);

  useEffect(() => {
    try {
      window.localStorage.removeItem(RESUME_KEY);
    } catch {
      // localStorage can be disabled; the success page should still render.
    }
  }, []);

  const claimSession = useCallback(async () => {
    if (!sessionId || sessionClaimed) return;
    try {
      const res = await api.claimSession(sessionId);
      if (res.status === 201) {
        setSessionClaimed(true);
        const data = res.data as { email?: string };
        if (data.email) setEmail(data.email);
      }
    } catch {
      // Claim failed - user can still log in manually.
    }
  }, [sessionId, sessionClaimed]);

  useEffect(() => {
    if (!sessionId) {
      setStatus("unknown");
      return;
    }
    if (status === "paid" || pollCount >= MAX_POLLS) return;

    const timer = setTimeout(async () => {
      try {
        const res = await api.checkoutStatus(sessionId);
        if (res.status === 200) {
          const data = res.data as { entitlement_state?: string; display_name?: string };
          if (data.display_name) setDisplayName(data.display_name);
          if (data.entitlement_state === "paid") {
            setStatus("paid");
            claimSession();
          } else {
            setPollCount((c) => c + 1);
          }
        } else {
          setPollCount((c) => c + 1);
        }
      } catch {
        setPollCount((c) => c + 1);
      }
    }, pollCount === 0 ? 500 : POLL_INTERVAL_MS);

    return () => clearTimeout(timer);
  }, [sessionId, status, pollCount, claimSession]);

  const confirmed = status === "paid";
  const timedOut = pollCount >= MAX_POLLS && status !== "paid";

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-signal-orange">
          {confirmed ? "Payment confirmed" : "Verifying payment"}
        </p>
        <h1 className="font-display text-3xl font-bold">
          {confirmed ? "Agent onboard ArcLink" : "Waiting for confirmation"}
        </h1>

        {!confirmed && !timedOut && (
          <div className="mt-4 flex items-center gap-3">
            <LoadingSpinner label="" />
            <p className="text-sm text-soft-white/65">
              Watching for Stripe webhook confirmation...
            </p>
          </div>
        )}

        {confirmed && (
          <div className="mt-4">
            <p className="text-sm text-soft-white/65">
              {displayName ? `Captain ${displayName}, ` : ""}Raven has confirmed payment and your ArcLink agent is entering the launch queue.
            </p>
            {sessionClaimed && (
              <p className="mt-2 text-sm text-neon-green">
                You are signed in{email ? ` as ${email}` : ""}.
              </p>
            )}
          </div>
        )}

        {timedOut && (
          <div className="mt-4">
            <p className="text-sm text-soft-white/65">
              Payment confirmation is taking longer than expected. This is normal - Stripe webhooks can take a few minutes.
            </p>
            <p className="mt-2 text-sm text-soft-white/65">
              You can safely close this page. Check your dashboard for status updates.
            </p>
          </div>
        )}

        <div className="mt-4">
          <StatusBadge status={confirmed ? "paid" : timedOut ? "pending" : "verifying"} />
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/dashboard"
            className="rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90"
          >
            Open Dashboard
          </Link>
          <Link
            href="/onboarding"
            className="rounded border border-border px-4 py-2 font-semibold text-soft-white transition hover:bg-carbon"
          >
            Add Another Agent
          </Link>
        </div>
      </section>
    </main>
  );
}
