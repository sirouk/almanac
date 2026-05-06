"use client";

import Link from "next/link";
import { useEffect } from "react";

const RESUME_KEY = "arclink_onboarding_resume";

export default function CheckoutSuccessPage() {
  useEffect(() => {
    try {
      window.localStorage.removeItem(RESUME_KEY);
    } catch {
      // localStorage can be disabled; the success page should still render.
    }
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-signal-orange">
          Stripe confirmation received
        </p>
        <h1 className="font-display text-3xl font-bold">Agent onboard ArcLink</h1>
        <p className="mt-4 text-sm text-soft-white/65">
          Raven is watching the payment confirmation and will move your ArcLink agent into the launch queue.
        </p>
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
