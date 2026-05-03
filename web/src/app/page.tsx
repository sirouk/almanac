"use client";

import Link from "next/link";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="font-display text-xl font-bold tracking-wide">
          <span className="text-signal-orange">ARC</span>LINK
        </div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm text-soft-white/60 hover:text-soft-white">
            Sign In
          </Link>
          <Link
            href="/onboarding"
            className="rounded bg-signal-orange px-4 py-2 text-sm font-semibold text-jet transition hover:opacity-90"
          >
            Take Me Aboard
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs uppercase tracking-[0.18em] text-soft-white/60">
          <span className="h-1.5 w-1.5 rounded-full bg-signal-orange" aria-hidden />
          Sovereign Cohort 001 — first 100 boarding
        </div>
        <h1 className="font-display text-4xl font-bold leading-tight sm:text-5xl md:text-6xl">
          I&apos;m Raven.<br />
          <span className="text-signal-orange">I&apos;ll bring ArcLink online.</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg text-soft-white/70">
          Give me a name, a mission, and a cleared Stripe handoff. I will turn that into your
          private ArcLink vessel: weapons-grade agents, SOTA inference rails, memory, retrieval,
          files, code tools, bot channels, and live deployment health. First agent $35/month.
        </p>
        <img
          src="/brand/raven/raven_hero.webp"
          alt=""
          className="mt-8 h-auto w-full max-w-2xl border border-border object-contain"
        />
        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <Link
            href="/onboarding"
            className="rounded bg-signal-orange px-6 py-3 text-base font-semibold text-jet transition hover:opacity-90"
          >
            Hire My First Agent
          </Link>
          <Link
            href="/dashboard"
            className="rounded border border-border px-6 py-3 text-base font-semibold text-soft-white transition hover:bg-surface"
          >
            Open Dashboard
          </Link>
        </div>
        <p className="mt-8 text-xs uppercase tracking-[0.22em] text-soft-white/40">
          Web · Telegram · Discord — same launch path, same Raven
        </p>
      </main>

      {/* Feature grid */}
      <section className="border-t border-border px-6 py-16">
        <div className="mx-auto mb-10 max-w-3xl text-center">
          <h2 className="font-display text-2xl font-semibold sm:text-3xl">What boards aboard your vessel</h2>
          <p className="mt-3 text-sm text-soft-white/60">
            Every pod ships fully wired. No infrastructure homework, no cobbled stack — Raven brings the hull online and hands you the helm.
          </p>
        </div>
        <div className="mx-auto grid max-w-5xl gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { title: "Hermes Agent", desc: "I give each pod a private assistant with memory, skills, and room to grow." },
            { title: "SOTA Model Rails", desc: "I start on Chutes and keep BYOK lanes open for the frontier models you trust." },
            { title: "qmd Retrieval", desc: "I keep the vault searchable so agents can pull the right context fast." },
            { title: "Managed Memory", desc: "I keep lightweight memory stubs hot so the vessel stays oriented." },
            { title: "Files & Code", desc: "I wire in Nextcloud and browser VS Code so your pod has hands, not just words." },
            { title: "Health & Ops", desc: "I watch DNS, billing, provisioning, and services so the launch path stays visible." },
          ].map((f) => (
            <div key={f.title} className="rounded-lg border border-border bg-surface p-6">
              <h3 className="font-display text-lg font-semibold text-signal-orange">{f.title}</h3>
              <p className="mt-2 text-sm text-soft-white/60">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-6 text-center text-sm text-soft-white/40">
        &copy; {new Date().getFullYear()} ArcLink. Private AI Infrastructure.
      </footer>
    </div>
  );
}
