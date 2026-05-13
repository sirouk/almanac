"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorAlert } from "@/components/ui";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.login({ email, password });
      if (res.status === 201) {
        router.push(res.data.session_kind === "admin" ? "/admin" : "/dashboard");
      } else {
        setError((res.data as Record<string, string>).error || "Login failed");
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
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          backgroundImage:
            "linear-gradient(rgba(251,80,5,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(251,80,5,0.028) 1px, transparent 1px)",
          backgroundSize: "76px 76px",
        }}
      />
      <div className="scan-line-hero" />

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
          href="/onboarding"
          className="rounded border border-white/10 px-4 py-2 font-mono text-xs font-semibold tracking-widest text-[#E7E6E6]/60 transition hover:border-[#FB5005]/35 hover:text-[#E7E6E6]"
        >
          GET STARTED
        </Link>
      </header>

      <main className="relative z-10 mx-auto grid min-h-[calc(100vh-96px)] max-w-6xl items-center gap-10 py-14 lg:grid-cols-[0.95fr_1.05fr]">
        <section className="hidden lg:block">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-[#FB5005]/25 px-3.5 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[#FB5005] status-blink" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-[#FB5005]/80">Secure Raven console</span>
          </div>
          <h1 className="font-heading max-w-xl text-5xl font-normal leading-[1.04] text-[#E7E6E6]">
            Return to the agent that runs your operations.
          </h1>
          <p className="font-body mt-6 max-w-lg text-base leading-relaxed text-[#E7E6E6]/50">
            Return to inspect provisioning, billing, workspace links, provider state, and the handoff credentials Raven prepared for your deployment.
          </p>
          <div className="relative mt-10 max-w-sm">
            <Image
              src="/marketing/raven-hero1.png"
              alt=""
              width={1254}
              height={1254}
              className="h-auto w-full object-contain opacity-90"
              sizes="384px"
              unoptimized
              priority
            />
          </div>
        </section>

        <section className="mx-auto w-full max-w-md rounded-lg border border-white/8 bg-[#0F0F0E]/95 p-8 shadow-[0_0_60px_rgba(251,80,5,0.08)] backdrop-blur">
          <p className="font-mono mb-2 text-[10px] uppercase tracking-[0.25em] text-[#FB5005]/70">ArcLink access</p>
          <h2 className="font-heading text-3xl font-normal text-[#E7E6E6]">Sign In</h2>
          <p className="font-body mt-2 text-sm text-[#E7E6E6]/40">Use your ArcLink credentials. Raven opens the right console for your account.</p>

          {error && <ErrorAlert message={error} className="mt-4" />}

          <form onSubmit={handleLogin} className="mt-6 space-y-4">
            <div>
              <label htmlFor="email" className="font-body block text-sm text-[#E7E6E6]/55">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded border border-white/10 bg-[#080808] px-3 py-2 text-[#E7E6E6] outline-none transition focus:border-[#FB5005]"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label htmlFor="password" className="font-body block text-sm text-[#E7E6E6]/55">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded border border-white/10 bg-[#080808] px-3 py-2 text-[#E7E6E6] outline-none transition focus:border-[#FB5005]"
                placeholder="Password"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-[#FB5005] px-4 py-3 font-body font-semibold text-white transition hover:bg-[#e04504] disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign In ->"}
            </button>
          </form>

          <p className="font-body mt-6 text-center text-xs text-[#E7E6E6]/30">
            No account?{" "}
            <Link href="/onboarding" className="text-[#FB5005] hover:underline">
              Start onboarding
            </Link>
          </p>
        </section>
      </main>
    </div>
  );
}
