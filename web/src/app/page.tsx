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
            Hire Agent
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="font-display text-4xl font-bold leading-tight sm:text-5xl md:text-6xl">
          Raven offers ArcLink:<br />
          <span className="text-signal-orange">your private ArcLink.</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg text-soft-white/70">
          Agents aboard a SOTA agentic harness at your fingertips, without making you leave the couch:
          Hermes agents, knowledge retrieval, managed memory, files, code tools, and bot integrations.
          First agent $35/month.
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
            Hire Your First Agent
          </Link>
          <Link
            href="/dashboard"
            className="rounded border border-border px-6 py-3 text-base font-semibold text-soft-white transition hover:bg-surface"
          >
            Open Dashboard
          </Link>
        </div>
      </main>

      {/* Feature grid */}
      <section className="border-t border-border px-6 py-16">
        <div className="mx-auto grid max-w-5xl gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { title: "Hermes Agent", desc: "Private AI assistant backed by your knowledge, memory, and skills." },
            { title: "qmd Retrieval", desc: "Structured document retrieval from your vault content." },
            { title: "Managed Memory", desc: "Persistent context synthesis across conversations." },
            { title: "Files & Code", desc: "Nextcloud storage and code-server IDE per deployment." },
            { title: "Bot Gateway", desc: "Telegram and Discord integrations with shared onboarding." },
            { title: "Health & Ops", desc: "Real-time service health, DNS, provisioning, and admin controls." },
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
