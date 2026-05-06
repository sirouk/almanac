"use client";

import Link from "next/link";

export default function CheckoutCancelPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-lg border border-border bg-surface p-8">
        <p className="mb-3 text-xs uppercase tracking-[0.22em] text-soft-white/40">
          Checkout paused
        </p>
        <h1 className="font-display text-3xl font-bold">No charge completed</h1>
        <p className="mt-4 text-sm text-soft-white/65">
          Your ArcLink onboarding is still here. Return when you are ready to bring the agent aboard.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/onboarding?resume=1"
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
