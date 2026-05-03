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
            Board ArcLink
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="font-display text-4xl font-bold leading-tight sm:text-5xl md:text-6xl">
          Raven guides you aboard<br />
          <span className="text-signal-orange">the ArcLink vessel.</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg text-soft-white/70">
          ArcLink is a private agentic harness: weapons-grade agents, SOTA inference rails,
          managed memory, retrieval, files, code tools, bot channels, and deployment health.
          Raven turns a few answers into a live pod. First agent $35/month.
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
            Hire First Agent
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
            { title: "SOTA Model Rails", desc: "Chutes-first inference with BYOK paths for frontier providers." },
            { title: "qmd Retrieval", desc: "Fast vault search that lets agents pull the right context on demand." },
            { title: "Managed Memory", desc: "Hot-swappable memory stubs that keep the vessel oriented." },
            { title: "Files & Code", desc: "Nextcloud storage and browser VS Code bound to each deployment." },
            { title: "Health & Ops", desc: "Live systems checks across DNS, provisioning, services, and billing." },
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
